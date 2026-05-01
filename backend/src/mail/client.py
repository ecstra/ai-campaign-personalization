"""Email sending client. Wraps Gmail SMTP for the scheduler and API."""

import os
import time
from typing import Optional

from dotenv import load_dotenv

from .base import Mail
from .gmail import send_gmail
from ..db.engine import get_cursor
from ..logger import logger

load_dotenv()

# Delay between sequential sends to respect Gmail rate limits
INTER_SEND_DELAY_MS = int(os.getenv("GMAIL_INTER_SEND_DELAY_MS", "200"))

# Daily send limit (consumer Gmail ~500, Workspace ~2000)
GMAIL_DAILY_SEND_LIMIT = int(os.getenv("GMAIL_DAILY_SEND_LIMIT", "450"))


def get_daily_send_count(user_id: str) -> int:
    """Count emails sent by this user in the last 24 hours."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM emails e
            JOIN leads l ON e.lead_id = l.id
            JOIN campaigns c ON l.campaign_id = c.id
            WHERE c.user_id = %s
              AND e.status = 'sent'
              AND e.sent_at >= NOW() - INTERVAL '24 hours'
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return row["count"] if row else 0


def check_already_sent(lead_id: str, sequence_number: int) -> bool:
    """Check if an email has already been sent for this lead + sequence. Idempotency guard."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id FROM emails
            WHERE lead_id = %s AND sequence_number = %s AND status = 'sent'
            """,
            (lead_id, sequence_number),
        )
        return cur.fetchone() is not None


def send_mail(
    mail: Mail,
    user_id: str,
    lead_id: str,
    sequence_number: int,
    in_reply_to: Optional[str] = None,
) -> Optional[str]:
    """
    Send a single email via Gmail SMTP. Records the result in the emails table.

    Returns:
        The Message-ID on success, None if skipped (already sent / rate limited).

    Raises:
        Exception on send failure after retries.
    """
    # Idempotency check
    if check_already_sent(lead_id, sequence_number):
        logger.info(f"Email already sent for lead {lead_id} seq {sequence_number}, skipping")
        return None

    message_id = send_gmail(
        user_id=user_id,
        from_email=mail.sender.email,
        from_name=mail.sender.name,
        to_email=mail.to,
        subject=mail.subject,
        html_body=mail.body,
        in_reply_to=in_reply_to,
    )

    return message_id


def send_mails_sequential(
    mails: list[dict],
    user_id: str,
) -> list[dict]:
    """
    Send a list of emails sequentially with a delay between sends.

    Each item in mails should contain:
        - mail: Mail object
        - lead_id: str
        - sequence_number: int
        - in_reply_to: Optional[str]

    Returns:
        List of result dicts: {lead_id, sequence_number, message_id, status, error}
    """
    results: list[dict] = []

    for i, item in enumerate(mails):
        mail: Mail = item["mail"]
        lead_id: str = item["lead_id"]
        sequence_number: int = item["sequence_number"]
        in_reply_to: Optional[str] = item.get("in_reply_to")

        try:
            message_id = send_mail(
                mail=mail,
                user_id=user_id,
                lead_id=lead_id,
                sequence_number=sequence_number,
                in_reply_to=in_reply_to,
            )

            results.append({
                "lead_id": lead_id,
                "sequence_number": sequence_number,
                "message_id": message_id,
                "status": "sent" if message_id else "skipped",
            })

        except Exception as e:
            logger.error(f"Failed to send email to lead {lead_id} seq {sequence_number}: {e}")
            results.append({
                "lead_id": lead_id,
                "sequence_number": sequence_number,
                "message_id": None,
                "status": "failed",
                "error": str(e),
            })

        # Delay between sends (skip after last email)
        if i < len(mails) - 1:
            time.sleep(INTER_SEND_DELAY_MS / 1000)

    return results
