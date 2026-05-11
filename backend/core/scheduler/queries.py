from typing import Any, Dict, List, Optional

from datetime import datetime
from psycopg2.extras import execute_batch, execute_values

from src.db import DatabaseEngine
from .config import LOCK_TIMEOUT_MINUTES, CAMPAIGN_EMAIL_RATE_LIMIT, RATE_LIMIT_WINDOW_MINUTES, MAX_LEADS_PER_RUN

class SchedulerQueryUtility:

    @staticmethod
    def get_eligible_leads() -> List[Dict[str, Any]]:
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

        with DatabaseEngine.get_cursor() as cur:
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

        return leads

    @staticmethod
    def lock_leads(lead_ids: List[str]) -> List[str]:
        if not lead_ids:
            return []

        with DatabaseEngine.get_cursor(commit=True) as cur:
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

    @staticmethod
    def check_replied_leads(lead_ids: List[str]) -> set[str]:
        if not lead_ids:
            return set()

        with DatabaseEngine.get_cursor() as cur:
            cur.execute(
                "SELECT id FROM leads WHERE id = ANY(%s::uuid[]) AND has_replied = true",
                (lead_ids,),
            )
            results = cur.fetchall()

        return {str(r["id"]) for r in results}

    @staticmethod
    def get_campaign_rate_limits(campaign_ids: List[str]) -> Dict[str, int]:
        if not campaign_ids:
            return {}

        with DatabaseEngine.get_cursor() as cur:
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

    @staticmethod
    def get_previous_emails_batch(lead_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        if not lead_ids:
            return {}

        with DatabaseEngine.get_cursor() as cur:
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

    @staticmethod
    def get_product_context_by_campaign(campaign_ids: List[str]) -> Dict[str, Optional[str]]:
        if not campaign_ids:
            return {}

        with DatabaseEngine.get_cursor() as cur:
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
            grouped.setdefault(cid, []).append(f"## Document: {row['name']}\n\n{brief}")

        return {
            cid: ("\n\n".join(parts) if parts else None)
            for cid, parts in grouped.items()
        } | {cid: None for cid in campaign_ids if cid not in grouped}

    @staticmethod
    def record_emails_batch(email_records: List[Dict[str, Any]]) -> None:
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

        with DatabaseEngine.get_cursor(commit=True) as cur:
            execute_values(
                cur,
                """
                INSERT INTO emails (lead_id, sequence_number, subject, body, status,
                                    message_id, in_reply_to, sent_at)
                VALUES %s
                """,
                values,
            )

    @staticmethod
    def update_leads_after_send(updates: List[Dict[str, Any]]) -> None:
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

        with DatabaseEngine.get_cursor(commit=True) as cur:
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

    @staticmethod
    def handle_generation_failures(failed_leads: List[Dict[str, Any]], error: str) -> None:
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

        with DatabaseEngine.get_cursor(commit=True) as cur:
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

    @staticmethod
    def check_campaign_completion(campaign_ids: list[str]) -> None:
        if not campaign_ids:
            return

        with DatabaseEngine.get_cursor(commit=True) as cur:
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
                (campaign_ids,),
            )

    @staticmethod
    def check_all_active_campaigns_completion() -> None:
        with DatabaseEngine.get_cursor(commit=True) as cur:
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

    @staticmethod
    def get_lead_earliest_sent_map(lead_ids: list[str]) -> dict[str, datetime]:
        if not lead_ids:
            return {}
        with DatabaseEngine.get_cursor() as cur:
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