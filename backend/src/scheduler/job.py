import asyncio
import email
import email.utils
import functools
import imaplib
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import execute_batch, execute_values
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from ..db import get_cursor
from ..auth.tokens import get_valid_access_token
from ..mail.agent import generate_mail
from ..mail.client import (
    send_mails_sequential,
    get_daily_send_count,
    GMAIL_DAILY_SEND_LIMIT,
)
from ..mail.base import Mail, Sender
from ..mail.imap import check_replies_for_user
from ..mail.replies import mark_lead_replied, extract_reply_text
from ..logger import logger

load_dotenv()

scheduler: AsyncIOScheduler | None = None

# Lock timeout in minutes (if a lead is locked for longer, consider it stale)
LOCK_TIMEOUT_MINUTES = 5

# How often to run the email processing job (in seconds)
JOB_INTERVAL_SECONDS = 60

# How often to check for replies via IMAP (in seconds)
REPLY_CHECK_INTERVAL_SECONDS = int(os.getenv("REPLY_CHECK_INTERVAL_SECONDS", "300"))

# Max leads to process per job run
MAX_LEADS_PER_RUN = 50

# Max concurrent AI generations
MAX_CONCURRENT_GENERATIONS = 10

# Per-campaign rate limit (kept for backward compat with stats endpoint)
CAMPAIGN_EMAIL_RATE_LIMIT = 50
RATE_LIMIT_WINDOW_MINUTES = 60


async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous function in executor to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(func, *args, **kwargs),
    )


# ── Eligible Leads Query ────────────────────────────────────────────────────


def _get_eligible_leads() -> List[Dict[str, Any]]:
    """
    Fetch leads eligible for email sending, including user context.

    Joins through campaigns -> users to get user_id and user_email.
    Only includes leads whose user has stored OAuth tokens (refresh_token_encrypted IS NOT NULL).

    Rate limits enforced twice for safety:
    1. HERE (query time): reduces unnecessary work
    2. Before sending: authoritative check
    """
    query = """
        WITH campaign_email_counts AS (
            SELECT
                l.campaign_id,
                COUNT(e.id) as emails_in_window
            FROM leads l
            JOIN emails e ON e.lead_id = l.id
            WHERE e.status = 'sent'
              AND e.sent_at >= NOW() - INTERVAL '%s minutes'
            GROUP BY l.campaign_id
        ),
        eligible_leads AS (
            SELECT
                l.id as lead_id,
                l.email,
                l.first_name,
                l.last_name,
                l.company,
                l.title,
                l.notes,
                l.current_sequence,
                l.next_email_at,
                c.id as campaign_id,
                c.name as campaign_name,
                c.sender_name,
                c.sender_email,
                c.goal,
                c.follow_up_delay_minutes,
                c.max_follow_ups,
                u.id as user_id,
                u.email as user_email,
                COALESCE(cec.emails_in_window, 0) as campaign_emails_in_window,
                ROW_NUMBER() OVER (
                    PARTITION BY c.id
                    ORDER BY l.next_email_at ASC NULLS FIRST
                ) as campaign_row_num
            FROM leads l
            JOIN campaigns c ON l.campaign_id = c.id
            JOIN users u ON c.user_id = u.id
            LEFT JOIN campaign_email_counts cec ON cec.campaign_id = c.id
            WHERE c.status = 'active'
              AND u.refresh_token_encrypted IS NOT NULL
              AND COALESCE(cec.emails_in_window, 0) < %s
              AND l.has_replied = false
              AND l.status NOT IN ('completed', 'replied', 'processing')
              AND l.current_sequence < c.max_follow_ups
              AND (l.next_email_at IS NULL OR l.next_email_at <= NOW())
              AND (l.locked_at IS NULL OR l.locked_at < NOW() - INTERVAL '%s minutes')
        )
        SELECT *
        FROM eligible_leads
        WHERE campaign_row_num <= (%s - campaign_emails_in_window)
        ORDER BY next_email_at ASC NULLS FIRST
        LIMIT %s
    """

    with get_cursor() as cur:
        cur.execute(
            query,
            (
                RATE_LIMIT_WINDOW_MINUTES,
                CAMPAIGN_EMAIL_RATE_LIMIT,
                LOCK_TIMEOUT_MINUTES,
                CAMPAIGN_EMAIL_RATE_LIMIT,
                MAX_LEADS_PER_RUN,
            ),
        )
        leads = cur.fetchall()

    return leads  # type: ignore


# ── Lead Locking ────────────────────────────────────────────────────────────


def _lock_leads(lead_ids: List[str]) -> List[str]:
    """Attempt to lock multiple leads for processing. Returns locked IDs."""
    if not lead_ids:
        return []

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE leads
            SET status = 'processing', locked_at = NOW(), updated_at = NOW()
            WHERE id = ANY(%s::uuid[])
              AND status NOT IN ('completed', 'replied', 'processing')
              AND (locked_at IS NULL OR locked_at < NOW() - INTERVAL '%s minutes')
            RETURNING id
            """,
            (lead_ids, LOCK_TIMEOUT_MINUTES),
        )
        results = cur.fetchall()

    return [str(r["id"]) for r in results]


def _check_replied_leads(lead_ids: List[str]) -> set[str]:
    """Check which leads have replied (final safety check before sending)."""
    if not lead_ids:
        return set()

    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM leads WHERE id = ANY(%s::uuid[]) AND has_replied = true",
            (lead_ids,),
        )
        results = cur.fetchall()

    return {str(r["id"]) for r in results}


# ── Rate Limiting ───────────────────────────────────────────────────────────


def _get_campaign_rate_limits(campaign_ids: List[str]) -> Dict[str, int]:
    """Authoritative per-campaign rate limit check right before sending."""
    if not campaign_ids:
        return {}

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id as campaign_id,
                %s - COALESCE((
                    SELECT COUNT(*)
                    FROM emails e
                    JOIN leads l ON e.lead_id = l.id
                    WHERE l.campaign_id = c.id
                      AND e.status = 'sent'
                      AND e.sent_at >= NOW() - INTERVAL '%s minutes'
                ), 0) as remaining
            FROM campaigns c
            WHERE c.id = ANY(%s::uuid[])
            """,
            (CAMPAIGN_EMAIL_RATE_LIMIT, RATE_LIMIT_WINDOW_MINUTES, campaign_ids),
        )
        results = cur.fetchall()

    return {str(r["campaign_id"]): max(0, r["remaining"]) for r in results}


# ── Previous Emails ─────────────────────────────────────────────────────────


def _get_previous_emails_batch(
    lead_ids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Get previous emails for multiple leads at once."""
    if not lead_ids:
        return {}

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT lead_id, sequence_number, subject, body, sent_at
            FROM emails
            WHERE lead_id = ANY(%s::uuid[]) AND status = 'sent'
            ORDER BY lead_id, sequence_number ASC
            """,
            (lead_ids,),
        )
        emails = cur.fetchall()

    result: Dict[str, List[Dict[str, Any]]] = {lid: [] for lid in lead_ids}
    for em in emails:
        lid = str(em["lead_id"])
        if lid in result:
            result[lid].append(em)

    return result


def _get_product_context_by_campaign(campaign_ids: List[str]) -> Dict[str, Optional[str]]:
    """
    Build the product-context string for each campaign by concatenating
    the briefs of its attached documents. Fetched once per send batch so
    leads sharing a campaign don't re-run the query.
    """
    if not campaign_ids:
        return {}

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT cd.campaign_id, d.name, d.brief
            FROM campaign_documents cd
            JOIN documents d ON cd.document_id = d.id
            WHERE cd.campaign_id = ANY(%s::uuid[])
            ORDER BY cd.campaign_id, cd.created_at ASC
            """,
            (campaign_ids,),
        )
        rows = cur.fetchall()

    grouped: Dict[str, List[str]] = {}
    for row in rows:
        cid = str(row["campaign_id"])
        brief = (row["brief"] or "").strip()
        if not brief:
            continue
        grouped.setdefault(cid, []).append(
            f"## Document: {row['name']}\n\n{brief}"
        )

    return {
        cid: ("\n\n".join(parts) if parts else None)
        for cid, parts in grouped.items()
    } | {cid: None for cid in campaign_ids if cid not in grouped}


# ── Record & Update ─────────────────────────────────────────────────────────


def _record_emails_batch(email_records: List[Dict[str, Any]]) -> None:
    """Record multiple emails in the database using batch insert."""
    if not email_records:
        return

    values = [
        (
            r["lead_id"],
            r["sequence_number"],
            r["subject"],
            r["body"],
            r["status"],
            r.get("message_id"),
            r.get("in_reply_to"),
            r.get("sent_at"),
        )
        for r in email_records
    ]

    with get_cursor(commit=True) as cur:
        execute_values(
            cur,
            """
            INSERT INTO emails (lead_id, sequence_number, subject, body, status,
                                message_id, in_reply_to, sent_at)
            VALUES %s
            """,
            values,
        )


def _update_leads_after_send(updates: List[Dict[str, Any]]) -> None:
    """Update multiple leads after successful email send."""
    if not updates:
        return

    params = [
        (
            u["new_sequence"],
            u["follow_up_delay_minutes"],
            "completed" if u["new_sequence"] >= u["max_follow_ups"] else "active",
            u["lead_id"],
        )
        for u in updates
    ]

    with get_cursor(commit=True) as cur:
        execute_batch(
            cur,
            """
            UPDATE leads
            SET current_sequence = %s,
                next_email_at = NOW() + INTERVAL '1 minute' * %s,
                status = %s,
                locked_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            """,
            params,
        )


# ── Failure Handling ────────────────────────────────────────────────────────


def _handle_generation_failures(
    failed_leads: List[Dict[str, Any]],
    error: str,
) -> None:
    """
    Handle leads that failed email generation.
    Increment current_sequence, record failure, retry if attempts remain.
    """
    if not failed_leads:
        return

    email_records = []
    lead_updates_terminal: list[str] = []
    lead_updates_retry: list[tuple[int, int, str]] = []

    for lead in failed_leads:
        lead_id = str(lead["lead_id"])
        new_sequence = lead["current_sequence"] + 1
        max_follow_ups = lead["max_follow_ups"]
        delay_minutes = lead["follow_up_delay_minutes"]

        email_records.append({
            "lead_id": lead_id,
            "sequence_number": new_sequence,
            "subject": "[FAILED] Generation error",
            "body": f"Error: {error}",
            "status": "failed",
            "message_id": None,
            "in_reply_to": None,
            "sent_at": None,
        })

        if new_sequence >= max_follow_ups:
            lead_updates_terminal.append(lead_id)
        else:
            lead_updates_retry.append((new_sequence, delay_minutes, lead_id))

    with get_cursor(commit=True) as cur:
        if email_records:
            values = [
                (r["lead_id"], r["sequence_number"], r["subject"], r["body"],
                 r["status"], r["message_id"], r["in_reply_to"], r["sent_at"])
                for r in email_records
            ]
            execute_values(
                cur,
                """
                INSERT INTO emails (lead_id, sequence_number, subject, body, status,
                                    message_id, in_reply_to, sent_at)
                VALUES %s
                """,
                values,
            )

        if lead_updates_terminal:
            cur.execute(
                """
                UPDATE leads
                SET status = 'failed', current_sequence = current_sequence + 1,
                    locked_at = NULL, updated_at = NOW()
                WHERE id = ANY(%s::uuid[])
                """,
                (lead_updates_terminal,),
            )
            logger.error(
                f"Leads terminally failed (max attempts exhausted): {lead_updates_terminal}"
            )

        if lead_updates_retry:
            execute_batch(
                cur,
                """
                UPDATE leads
                SET status = 'pending',
                    current_sequence = %s,
                    next_email_at = NOW() + INTERVAL '1 minute' * %s,
                    locked_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                lead_updates_retry,
            )
            logger.warning(
                f"Leads scheduled for retry: {[u[2] for u in lead_updates_retry]}"
            )


# ── Campaign Completion ─────────────────────────────────────────────────────


def _check_campaign_completion(campaign_ids: List[str]) -> None:
    """Mark campaigns as completed when all their leads are in terminal states."""
    if not campaign_ids:
        return

    unique_ids = list(set(campaign_ids))

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE campaigns c
            SET status = 'completed', updated_at = NOW()
            WHERE c.id = ANY(%s::uuid[])
              AND c.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM leads l
                  WHERE l.campaign_id = c.id
                    AND l.status NOT IN ('completed', 'replied', 'failed')
              )
            """,
            (unique_ids,),
        )


def _check_all_active_campaigns_completion() -> None:
    """Safety net: check ALL active campaigns for completion."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE campaigns c
            SET status = 'completed', updated_at = NOW()
            WHERE c.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM leads l
                  WHERE l.campaign_id = c.id
                    AND l.status NOT IN ('completed', 'replied', 'failed')
              )
            """
        )


# ── Email Generation ────────────────────────────────────────────────────────


async def generate_email_for_lead(
    lead: Dict[str, Any],
    previous_emails: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Exception]]:
    """Generate personalized email for a single lead."""
    lead_id = str(lead["lead_id"])

    try:
        user_info = {
            "email": lead["email"],
            "first_name": lead["first_name"],
            "last_name": lead["last_name"],
            "company": lead["company"],
            "title": lead["title"],
            "notes": lead["notes"],
        }

        campaign_info = {
            "name": lead["campaign_name"],
            "goal": lead["goal"],
            # Injected by the send batch via _get_product_context_by_campaign
            # so every lead in the same campaign shares one context string
            # without re-querying per lead.
            "product_context": lead.get("_product_context"),
            "sender_name": lead["sender_name"],
            "sender_email": lead["sender_email"],
            "current_sequence": lead["current_sequence"] + 1,
            "max_follow_ups": lead["max_follow_ups"],
        }

        # Limit context to last 5 emails
        recent_emails = previous_emails[-5:] if len(previous_emails) > 5 else previous_emails
        personalized = await generate_mail(user_info, campaign_info, recent_emails)

        email_data = {
            "lead_id": lead_id,
            "lead": lead,
            "subject": personalized.subject,
            "body": personalized.body,
            "sequence_number": lead["current_sequence"] + 1,
        }

        return (lead, email_data, None)

    except Exception as e:
        logger.error(f"Failed to generate email for lead {lead_id}: {e}")
        return (lead, None, e)


# ── Main Job: Process Leads ─────────────────────────────────────────────────


def _build_imap_xoauth2(user_email: str, access_token: str) -> bytes:
    """Build XOAUTH2 auth string for IMAP."""
    return f"user={user_email}\x01auth=Bearer {access_token}\x01\x01".encode()


def _get_lead_earliest_sent_map(lead_ids: list[str]) -> dict[str, datetime]:
    """Return earliest sent_at per lead_id for the given lead_ids."""
    if not lead_ids:
        return {}
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT lead_id, MIN(sent_at) AS earliest_sent_at
            FROM emails
            WHERE lead_id = ANY(%s::uuid[]) AND status = 'sent'
            GROUP BY lead_id
            """,
            (lead_ids,),
        )
        rows = cur.fetchall()
    return {str(row["lead_id"]): row["earliest_sent_at"] for row in rows}


def _targeted_reply_check(
    user_id: str,
    user_email: str,
    lead_emails: list[str],
    lead_email_to_id: dict[str, str],
) -> set[str]:
    """
    Lightweight IMAP check for replies from a small set of specific lead addresses.
    Called right before sending follow-ups to a user. Only searches for emails from
    the leads we're about to send to, not the entire inbox.

    Guards against stale matches: an email from a lead dated BEFORE we first
    sent them anything cannot be a reply to anything we sent. Without this
    guard, old replies from previous campaigns (where the same address appeared
    as a lead) would taint a new campaign's leads.

    Returns set of lead_ids that have replied.
    """
    if not lead_emails:
        return set()

    replied_lead_ids: set[str] = set()

    # Earliest sent timestamps for the leads we're about to check. If a lead
    # has no sent email at all, there is nothing a reply could be a response to.
    earliest_sent = _get_lead_earliest_sent_map(list(lead_email_to_id.values()))

    try:
        access_token = get_valid_access_token(user_id)
        auth_string = _build_imap_xoauth2(user_email, access_token)

        imap_conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap_conn.authenticate("XOAUTH2", lambda _: auth_string)
        imap_conn.select("INBOX", readonly=True)

        try:
            if len(lead_emails) == 1:
                from_criteria = f'FROM "{lead_emails[0]}"'
            else:
                from_criteria = f'FROM "{lead_emails[0]}"'
                for addr in lead_emails[1:]:
                    from_criteria = f'OR ({from_criteria}) (FROM "{addr}")'

            status, msg_nums = imap_conn.search(None, f"({from_criteria})")
            if status == "OK" and msg_nums[0]:
                for num in msg_nums[0].split():
                    status, data = imap_conn.fetch(num, "(RFC822.HEADER)")
                    if status != "OK" or not data:
                        continue
                    for part in data:
                        if isinstance(part, tuple) and b"HEADER" in part[0]:
                            msg = email.message_from_bytes(part[1])
                            from_addr = email.utils.parseaddr(msg.get("From", ""))[1].lower()
                            if from_addr not in lead_email_to_id:
                                continue

                            lead_id = lead_email_to_id[from_addr]
                            lead_earliest = earliest_sent.get(lead_id)
                            if not lead_earliest:
                                # Never sent anything to this lead — any "reply"
                                # is necessarily unrelated to this campaign.
                                continue

                            reply_date: Optional[datetime] = None
                            date_header = msg.get("Date", "")
                            if date_header:
                                try:
                                    reply_date = email.utils.parsedate_to_datetime(date_header)
                                except (TypeError, ValueError):
                                    reply_date = None

                            if not reply_date or reply_date < lead_earliest:
                                logger.info(
                                    f"[CRON] Skipping stale sender-match for lead {lead_id}: "
                                    f"reply_date={reply_date}, earliest_sent={lead_earliest}"
                                )
                                continue

                            replied_lead_ids.add(lead_id)
                            mark_lead_replied(
                                lead_id=lead_id,
                                subject=msg.get("Subject", ""),
                                reply_content="(detected pre-send)",
                                gmail_message_id=msg.get("Message-ID", ""),
                                received_at=reply_date,
                            )
        finally:
            imap_conn.logout()

    except Exception as e:
        logger.warning(f"[CRON] Targeted reply check failed for user {user_id}: {e}")

    return replied_lead_ids


async def process_leads_job() -> None:
    """
    Main email processing job.

    Flow:
    0. Check for replies FIRST (prevents sending to leads who just replied)
    1. Fetch eligible leads (with user context)
    2. Check per-user daily Gmail limits
    3. Lock leads
    4. Fetch previous emails for context
    5. Generate emails concurrently via LLM
    6. Enforce per-campaign rate limits (authoritative)
    7. Send emails sequentially per user via Gmail SMTP
    8. Record results and update leads
    9. Check campaign completion
    """
    try:
        # Step 1: Fetch eligible leads
        leads = await run_sync(_get_eligible_leads)
        if not leads:
            return

        # Step 2: Check per-user daily limits and filter
        user_ids = list({str(lead["user_id"]) for lead in leads})
        user_daily_counts: Dict[str, int] = {}
        for uid in user_ids:
            user_daily_counts[uid] = await run_sync(get_daily_send_count, uid)

        # Filter out leads from users who have hit their daily limit
        leads_within_limit: list[Dict[str, Any]] = []
        user_remaining: Dict[str, int] = {}

        for uid in user_ids:
            user_remaining[uid] = max(0, GMAIL_DAILY_SEND_LIMIT - user_daily_counts.get(uid, 0))

        for lead in leads:
            uid = str(lead["user_id"])
            if user_remaining.get(uid, 0) > 0:
                leads_within_limit.append(lead)
                user_remaining[uid] -= 1

        if not leads_within_limit:
            logger.info("[CRON] All users at daily Gmail limit, skipping")
            return

        leads = leads_within_limit

        # Step 3: Lock leads
        lead_ids = [str(lead["lead_id"]) for lead in leads]
        locked_ids = await run_sync(_lock_leads, lead_ids)

        if not locked_ids:
            logger.warning("[CRON] Failed to lock leads (already processing)")
            return

        locked_leads = [l for l in leads if str(l["lead_id"]) in locked_ids]

        # Step 4: Fetch previous emails + per-campaign product context
        previous_emails_map = await run_sync(_get_previous_emails_batch, locked_ids)
        unique_campaign_ids = list({str(l["campaign_id"]) for l in locked_leads})
        product_context_map = await run_sync(
            _get_product_context_by_campaign, unique_campaign_ids
        )

        # Step 5: Generate emails concurrently
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

        async def generate_with_semaphore(lead: Dict[str, Any]) -> Any:
            async with semaphore:
                prev_emails = previous_emails_map.get(str(lead["lead_id"]), [])
                lead["_product_context"] = product_context_map.get(str(lead["campaign_id"]))
                return await generate_email_for_lead(lead, prev_emails)

        generation_results = await asyncio.gather(
            *[generate_with_semaphore(lead) for lead in locked_leads],
            return_exceptions=True,
        )

        successful_generations: List[Dict[str, Any]] = []
        failed_leads: List[Dict[str, Any]] = []

        for result in generation_results:
            if isinstance(result, Exception):
                continue
            lead, email_data, error = result  # type: ignore
            if error or email_data is None:
                failed_leads.append(lead)
            else:
                successful_generations.append(email_data)

        if failed_leads:
            logger.warning(f"[CRON] {len(failed_leads)} leads failed generation")
            await run_sync(
                _handle_generation_failures, failed_leads, "Email generation failed"
            )

        if not successful_generations:
            return

        # Step 6: Enforce per-campaign rate limits (authoritative)
        campaign_ids = list(
            {gen["lead"]["campaign_id"] for gen in successful_generations}
        )
        rate_limits = await run_sync(_get_campaign_rate_limits, campaign_ids)

        campaign_gens: Dict[str, List[Dict[str, Any]]] = {}
        for gen in successful_generations:
            cid = gen["lead"]["campaign_id"]
            if cid not in campaign_gens:
                campaign_gens[cid] = []
            campaign_gens[cid].append(gen)

        filtered_generations: List[Dict[str, Any]] = []
        skipped_leads: List[Dict[str, Any]] = []

        for cid, gens in campaign_gens.items():
            remaining = rate_limits.get(cid, 0)
            if remaining <= 0:
                skipped_leads.extend([g["lead"] for g in gens])
            elif len(gens) > remaining:
                filtered_generations.extend(gens[:remaining])
                skipped_leads.extend([g["lead"] for g in gens[remaining:]])
            else:
                filtered_generations.extend(gens)

        # Unlock skipped leads for next run
        if skipped_leads:
            skipped_ids = [str(l["lead_id"]) for l in skipped_leads]
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    UPDATE leads
                    SET status = 'active', locked_at = NULL, updated_at = NOW()
                    WHERE id = ANY(%s::uuid[])
                    """,
                    (skipped_ids,),
                )

        if not filtered_generations:
            return

        successful_generations = filtered_generations

        # Step 6b: Final replied-leads safety check
        gen_lead_ids = [str(gen["lead"]["lead_id"]) for gen in successful_generations]
        replied_ids = await run_sync(_check_replied_leads, gen_lead_ids)

        if replied_ids:
            successful_generations = [
                gen
                for gen in successful_generations
                if str(gen["lead"]["lead_id"]) not in replied_ids
            ]
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    UPDATE leads
                    SET status = 'replied', locked_at = NULL, updated_at = NOW()
                    WHERE id = ANY(%s::uuid[])
                    """,
                    (list(replied_ids),),
                )

        if not successful_generations:
            return

        # Step 7: Send emails per user via Gmail SMTP
        # Group by user_id for sequential per-user sending
        user_gen_groups: Dict[str, List[Dict[str, Any]]] = {}
        for gen in successful_generations:
            uid = str(gen["lead"]["user_id"])
            if uid not in user_gen_groups:
                user_gen_groups[uid] = []
            user_gen_groups[uid].append(gen)

        all_email_records: List[Dict[str, Any]] = []
        all_lead_updates: List[Dict[str, Any]] = []
        all_send_failures: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for uid, gens in user_gen_groups.items():
            # Targeted reply check: only for leads we're about to email
            user_email_for_check = gens[0]["lead"]["sender_email"]
            lead_emails_to_check = [g["lead"]["email"].lower() for g in gens]
            lead_email_to_id_map = {g["lead"]["email"].lower(): g["lead_id"] for g in gens}

            try:
                just_replied = await run_sync(
                    _targeted_reply_check, uid, user_email_for_check,
                    lead_emails_to_check, lead_email_to_id_map,
                )
                if just_replied:
                    logger.info(f"[CRON] Pre-send check caught {len(just_replied)} replies for user {uid}")
                    gens = [g for g in gens if g["lead_id"] not in just_replied]
                    if not gens:
                        continue
            except Exception as e:
                logger.warning(f"[CRON] Targeted reply check failed for user {uid}: {e}")

            # Get the last sent message_id and the original subject per lead for threading
            lead_ids_in_group = [gen["lead_id"] for gen in gens]
            last_message_ids: Dict[str, Optional[str]] = {}
            original_subjects: Dict[str, str] = {}
            with get_cursor() as cur:
                # Last message_id for In-Reply-To header
                cur.execute(
                    """
                    SELECT DISTINCT ON (lead_id) lead_id, message_id
                    FROM emails
                    WHERE lead_id = ANY(%s::uuid[]) AND status = 'sent' AND message_id IS NOT NULL
                    ORDER BY lead_id, sequence_number DESC
                    """,
                    (lead_ids_in_group,),
                )
                for row in cur.fetchall():
                    last_message_ids[str(row["lead_id"])] = row["message_id"]

                # First email subject for thread consistency
                cur.execute(
                    """
                    SELECT DISTINCT ON (lead_id) lead_id, subject
                    FROM emails
                    WHERE lead_id = ANY(%s::uuid[]) AND status = 'sent'
                    ORDER BY lead_id, sequence_number ASC
                    """,
                    (lead_ids_in_group,),
                )
                for row in cur.fetchall():
                    original_subjects[str(row["lead_id"])] = row["subject"]

            # Build mail list for this user
            mails_to_send = []
            for gen in gens:
                lead = gen["lead"]
                lead_id = gen["lead_id"]

                # For follow-ups, use "Re: {original subject}" to maintain thread
                subject = gen["subject"]
                if lead_id in original_subjects and gen["sequence_number"] > 1:
                    orig = original_subjects[lead_id]
                    # Don't double-prefix if LLM already added "Re:"
                    if not subject.lower().startswith("re:"):
                        subject = f"Re: {orig}"

                mail = Mail(
                    sender=Sender(name=lead["sender_name"], email=lead["sender_email"]),
                    to=lead["email"],
                    subject=subject,
                    body=gen["body"],
                )
                mails_to_send.append({
                    "mail": mail,
                    "lead_id": lead_id,
                    "sequence_number": gen["sequence_number"],
                    "in_reply_to": last_message_ids.get(lead_id),
                })

            try:
                send_results = await run_sync(send_mails_sequential, mails_to_send, uid)

                for sr in send_results:
                    if sr["status"] == "sent":
                        all_email_records.append({
                            "lead_id": sr["lead_id"],
                            "sequence_number": sr["sequence_number"],
                            "subject": next(
                                g["subject"] for g in gens if g["lead_id"] == sr["lead_id"]
                            ),
                            "body": next(
                                g["body"] for g in gens if g["lead_id"] == sr["lead_id"]
                            ),
                            "status": "sent",
                            "message_id": sr["message_id"],
                            "in_reply_to": last_message_ids.get(sr["lead_id"]),
                            "sent_at": now,
                        })

                        matching_gen = next(
                            g for g in gens if g["lead_id"] == sr["lead_id"]
                        )
                        all_lead_updates.append({
                            "lead_id": sr["lead_id"],
                            "new_sequence": sr["sequence_number"],
                            "max_follow_ups": matching_gen["lead"]["max_follow_ups"],
                            "follow_up_delay_minutes": matching_gen["lead"]["follow_up_delay_minutes"],
                        })
                    elif sr["status"] == "failed":
                        matching_lead = next(
                            g["lead"] for g in gens if g["lead_id"] == sr["lead_id"]
                        )
                        all_send_failures.append(matching_lead)
                    # "skipped" means already sent (idempotency), no action needed

            except Exception as e:
                logger.error(f"[CRON] Send failed for user {uid}: {e}")
                all_send_failures.extend([g["lead"] for g in gens])

        # Step 8: Record results
        if all_email_records:
            await run_sync(_record_emails_batch, all_email_records)
        if all_lead_updates:
            await run_sync(_update_leads_after_send, all_lead_updates)
        if all_send_failures:
            await run_sync(
                _handle_generation_failures,
                all_send_failures,
                "Gmail send failed",
            )

        # Step 9: Check campaign completion
        all_campaign_ids = list(
            {gen["lead"]["campaign_id"] for gen in successful_generations}
        )
        await run_sync(_check_campaign_completion, all_campaign_ids)

    except Exception as e:
        logger.error(f"[CRON] Email processing job failed: {e}")

    finally:
        await run_sync(_check_all_active_campaigns_completion)


# ── Reply Checking Job ──────────────────────────────────────────────────────


async def check_replies_job() -> None:
    """
    Periodic job that checks for replies via IMAP for all users
    with active campaigns.
    """
    try:
        # Get all users with active campaigns that have unreplied leads
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT u.id as user_id, u.email as user_email
                FROM users u
                JOIN campaigns c ON c.user_id = u.id
                JOIN leads l ON l.campaign_id = c.id
                WHERE c.status = 'active'
                  AND l.has_replied = false
                  AND l.status NOT IN ('replied', 'failed')
                  AND u.refresh_token_encrypted IS NOT NULL
                """
            )
            users = cur.fetchall()

        if not users:
            return

        logger.info(f"[REPLY-CHECK] Checking replies for {len(users)} users")

        # Process users sequentially to avoid overwhelming IMAP connections
        for user in users:
            uid = str(user["user_id"])
            user_email = user["user_email"]

            try:
                replies = await run_sync(check_replies_for_user, uid, user_email)

                for reply in replies:
                    reply_body = extract_reply_text(reply.get("body", ""))
                    mark_lead_replied(
                        lead_id=reply["lead_id"],
                        subject=reply.get("subject", ""),
                        reply_content=reply_body or "(Reply content unavailable)",
                        gmail_message_id=reply.get("gmail_message_id"),
                        received_at=reply.get("received_at"),
                    )

                if replies:
                    logger.info(
                        f"[REPLY-CHECK] Found {len(replies)} replies for user {uid}"
                    )

                    # Check campaign completion after processing replies
                    campaign_ids: list[str] = []
                    with get_cursor() as cur:
                        cur.execute(
                            """
                            SELECT DISTINCT c.id
                            FROM campaigns c
                            WHERE c.user_id = %s AND c.status = 'active'
                            """,
                            (uid,),
                        )
                        campaign_ids = [str(r["id"]) for r in cur.fetchall()]

                    if campaign_ids:
                        _check_campaign_completion(campaign_ids)

            except Exception as e:
                logger.error(f"[REPLY-CHECK] Failed for user {uid}: {e}")
                continue

    except Exception as e:
        logger.error(f"[REPLY-CHECK] Reply checking job failed: {e}")


# ── Scheduled Campaign Auto-Start ───────────────────────────────────────────


async def check_scheduled_campaigns() -> None:
    """
    Auto-start campaigns whose scheduled_start_at has passed.
    Runs every 60s. Activates draft campaigns and queues their pending leads.
    """
    try:
        with get_cursor(commit=True) as cur:
            # Find draft campaigns whose scheduled time has arrived
            cur.execute(
                """
                SELECT id FROM campaigns
                WHERE status = 'draft'
                  AND scheduled_start_at IS NOT NULL
                  AND scheduled_start_at <= NOW()
                """
            )
            campaigns = cur.fetchall()

            for campaign in campaigns:
                cid = str(campaign["id"])

                # Check campaign has leads
                cur.execute("SELECT COUNT(*) as count FROM leads WHERE campaign_id = %s", (cid,))
                if cur.fetchone()["count"] == 0:
                    logger.warning(f"[SCHEDULE] Campaign {cid} scheduled but has no leads, skipping")
                    continue

                # Activate campaign
                cur.execute(
                    "UPDATE campaigns SET status = 'active', updated_at = NOW() WHERE id = %s",
                    (cid,),
                )

                # Queue pending leads
                cur.execute(
                    """
                    UPDATE leads
                    SET next_email_at = NOW(), updated_at = NOW()
                    WHERE campaign_id = %s AND status = 'pending' AND next_email_at IS NULL
                    """,
                    (cid,),
                )

                logger.info(f"[SCHEDULE] Auto-started campaign {cid}")

    except Exception as e:
        logger.error(f"[SCHEDULE] Scheduled campaign check failed: {e}")


# ── Scheduler Lifecycle ─────────────────────────────────────────────────────


def start_scheduler() -> None:
    """Start the background scheduler with email processing and reply checking jobs."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already running. Won't start a new one.")
        return

    scheduler = AsyncIOScheduler()

    # Email processing job: runs every 60 seconds
    scheduler.add_job(
        process_leads_job,
        trigger=IntervalTrigger(seconds=JOB_INTERVAL_SECONDS),
        id="email_processing_job",
        name="Process pending emails",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    # Reply checking job: runs every 60s (configurable)
    scheduler.add_job(
        check_replies_job,
        trigger=IntervalTrigger(seconds=REPLY_CHECK_INTERVAL_SECONDS),
        id="reply_checking_job",
        name="Check for email replies via IMAP",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    # Scheduled campaign auto-start: runs every 60s
    scheduler.add_job(
        check_scheduled_campaigns,
        trigger=IntervalTrigger(seconds=60),
        id="scheduled_campaign_job",
        name="Auto-start scheduled campaigns",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.start()
    logger.info(
        f"Scheduler started: emails every {JOB_INTERVAL_SECONDS}s, "
        f"reply check every {REPLY_CHECK_INTERVAL_SECONDS}s"
    )


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global scheduler

    if scheduler is None:
        logger.warning("Scheduler not running. Shutdown not needed.")
        return

    scheduler.shutdown(wait=False)
    scheduler = None
    logger.info("Scheduler stopped")
