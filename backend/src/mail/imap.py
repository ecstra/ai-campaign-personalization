"""Gmail IMAP reply detection via XOAUTH2 authentication."""

import base64
import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Optional

from ..auth.tokens import get_valid_access_token
from ..db.engine import get_cursor
from ..logger import logger
from .replies import extract_reply_html, extract_reply_text

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


def _build_xoauth2_string(user_email: str, access_token: str) -> bytes:
    auth_string = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return auth_string.encode()


def _decode_header_value(raw: Optional[str]) -> str:
    """Decode an email header that may be MIME-encoded."""
    if not raw:
        return ""
    decoded_parts = decode_header(raw)
    parts: list[str] = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return " ".join(parts)


def _extract_clean_body(msg: email.message.Message) -> str:
    """
    Walk a parsed MIME message and return a clean reply body with quotes stripped.
    Prefers text/plain; falls back to stripping HTML if only text/html is available.
    """
    plain_text: Optional[str] = None
    html_text: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and plain_text is None:
                plain_text = decoded
            elif ctype == "text/html" and html_text is None:
                html_text = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_text = decoded
            else:
                plain_text = decoded

    if plain_text:
        return extract_reply_text(plain_text)
    if html_text:
        # Strip HTML tags after removing quoted sections
        cleaned_html = extract_reply_html(html_text)
        stripped = re.sub(r"<[^>]+>", "", cleaned_html)
        stripped = re.sub(r"\s+\n", "\n", stripped)
        return stripped.strip()
    return ""


def _get_lead_emails_for_user(user_id: str) -> dict[str, list[dict]]:
    """
    Fetch all lead email addresses for active campaigns of this user,
    along with the message_ids of emails we sent to them.

    Returns:
        Dict mapping lead email address -> list of {lead_id, message_id, sequence_number}
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                l.id as lead_id,
                l.email as lead_email,
                e.message_id,
                e.sequence_number
            FROM leads l
            JOIN campaigns c ON l.campaign_id = c.id
            LEFT JOIN emails e ON e.lead_id = l.id AND e.status = 'sent'
            WHERE c.user_id = %s
              AND c.status = 'active'
              AND l.has_replied = false
              AND l.status NOT IN ('replied', 'failed')
            ORDER BY l.email, e.sequence_number
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    lead_map: dict[str, list[dict]] = {}
    for row in rows:
        addr = row["lead_email"].lower()
        if addr not in lead_map:
            lead_map[addr] = []
        if row["message_id"]:
            lead_map[addr].append({
                "lead_id": str(row["lead_id"]),
                "message_id": row["message_id"],
                "sequence_number": row["sequence_number"],
            })

    return lead_map


def _get_lead_earliest_sent(user_id: str) -> dict[str, datetime]:
    """
    For every lead in the user's active campaigns, return the earliest
    timestamp at which we sent them an email (status='sent').

    Used to guard against cross-campaign reply pollution when the sender-
    email fallback is the only match: a reply dated before we ever sent
    anything to this lead cannot be a response to anything we sent.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.id AS lead_id, MIN(e.sent_at) AS earliest_sent_at
            FROM leads l
            JOIN campaigns c ON l.campaign_id = c.id
            JOIN emails e ON e.lead_id = l.id AND e.status = 'sent'
            WHERE c.user_id = %s AND c.status = 'active'
            GROUP BY l.id
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {str(row["lead_id"]): row["earliest_sent_at"] for row in rows}


def _get_earliest_campaign_start(user_id: str) -> Optional[datetime]:
    """Get the earliest active campaign start date to scope the IMAP search."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT MIN(c.updated_at) as earliest
            FROM campaigns c
            WHERE c.user_id = %s AND c.status = 'active'
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if row and row["earliest"]:
        return row["earliest"]
    return None


def check_replies_for_user(user_id: str, user_email: str) -> list[dict]:
    """
    Connect to the user's Gmail via IMAP XOAUTH2 and check for replies
    from lead email addresses. Matches replies using In-Reply-To headers.

    Returns:
        List of dicts: {lead_id, subject, body, gmail_message_id}
    """
    lead_map = _get_lead_emails_for_user(user_id)
    if not lead_map:
        return []

    earliest_start = _get_earliest_campaign_start(user_id)
    if not earliest_start:
        return []

    # Per-lead earliest sent timestamp. Sender-fallback matches that predate
    # the earliest sent email for the matched lead are rejected as stale.
    lead_earliest_sent = _get_lead_earliest_sent(user_id)

    # Search IMAP since a day before earliest campaign start
    since_date = (earliest_start - timedelta(days=1)).strftime("%d-%b-%Y")

    access_token = get_valid_access_token(user_id)
    auth_string = _build_xoauth2_string(user_email, access_token)

    imap: Optional[imaplib.IMAP4_SSL] = None
    replies: list[dict] = []

    try:
        imap = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        imap.authenticate("XOAUTH2", lambda _: auth_string)
        imap.select("INBOX", readonly=True)

        # Build IMAP search: emails FROM any lead address, since campaign start
        # IMAP OR syntax: (OR (FROM "a") (FROM "b")) for 2 addresses,
        # nested for more: (OR (OR (FROM "a") (FROM "b")) (FROM "c"))
        lead_addrs = list(lead_map.keys())

        if len(lead_addrs) == 1:
            from_criteria = f'FROM "{lead_addrs[0]}"'
        else:
            # Build nested OR tree
            from_criteria = f'FROM "{lead_addrs[0]}"'
            for addr in lead_addrs[1:]:
                from_criteria = f'OR ({from_criteria}) (FROM "{addr}")'

        search_query = f"({from_criteria} SINCE {since_date})"

        status, msg_nums = imap.search(None, search_query)
        if status != "OK" or not msg_nums[0]:
            return []

        msg_id_list = msg_nums[0].split()
        logger.info(
            f"IMAP found {len(msg_id_list)} candidate messages for user {user_id}"
        )

        # Build a lookup of our sent message_ids to lead info
        sent_msg_lookup: dict[str, dict] = {}
        for addr, entries in lead_map.items():
            for entry in entries:
                if entry["message_id"]:
                    sent_msg_lookup[entry["message_id"]] = {
                        "lead_id": entry["lead_id"],
                        "lead_email": addr,
                    }

        for num in msg_id_list:
            status, data = imap.fetch(num, "(RFC822)")
            if status != "OK" or not data:
                continue

            # RFC822 returns the full raw message bytes in the first tuple element
            raw_message: Optional[bytes] = None
            for part in data:
                if isinstance(part, tuple) and len(part) >= 2:
                    raw_message = part[1]
                    break

            if not raw_message:
                continue

            msg = email.message_from_bytes(raw_message)
            in_reply_to = msg.get("In-Reply-To", "").strip()
            references = msg.get("References", "").strip()
            from_addr = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            subject = _decode_header_value(msg.get("Subject"))
            gmail_message_id = msg.get("Message-ID", "").strip()
            reply_date_header = msg.get("Date", "")
            reply_date: Optional[datetime] = None
            if reply_date_header:
                try:
                    reply_date = email.utils.parsedate_to_datetime(reply_date_header)
                except (TypeError, ValueError):
                    reply_date = None

            # Match by In-Reply-To header
            matched_lead = sent_msg_lookup.get(in_reply_to)

            # Fallback: check References header chain
            if not matched_lead and references:
                for ref in references.split():
                    matched_lead = sent_msg_lookup.get(ref.strip())
                    if matched_lead:
                        break

            # Fallback: match by sender email if they're a known lead.
            # Guard: only accept this match if the reply is dated AFTER the
            # earliest email we ever sent to this lead. This kills cross-
            # campaign pollution where an old reply (from a prior campaign)
            # still sits in the user's inbox.
            if not matched_lead and from_addr in lead_map and lead_map[from_addr]:
                candidate_lead_id = lead_map[from_addr][0]["lead_id"]
                earliest_sent = lead_earliest_sent.get(candidate_lead_id)
                if earliest_sent and reply_date and reply_date >= earliest_sent:
                    matched_lead = {
                        "lead_id": candidate_lead_id,
                        "lead_email": from_addr,
                    }
                else:
                    logger.info(
                        f"Skipping sender-fallback match for lead {candidate_lead_id}: "
                        f"reply_date={reply_date}, earliest_sent={earliest_sent}"
                    )

            if matched_lead:
                body_text = _extract_clean_body(msg)
                replies.append({
                    "lead_id": matched_lead["lead_id"],
                    "subject": subject,
                    "body": body_text,
                    "gmail_message_id": gmail_message_id,
                    "received_at": reply_date,
                })

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error for user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking replies for user {user_id}: {e}")
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass

    return replies
