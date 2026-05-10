import asyncio
import functools
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.db import DatabaseEngine
from core.mail import MailAgentUtility, MailClientUtility, GMAIL_DAILY_SEND_LIMIT, Mail, Sender, ImapUtility, ReplyUtility
from .config import MAX_CONCURRENT_GENERATIONS
from .queries import SchedulerQueryUtility

logger = logging.getLogger(__name__)

class SchedulerProcessorUtility:

    @staticmethod
    async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(func, *args, **kwargs),
        )

    @staticmethod
    async def generate_email_for_lead(
        lead: Dict[str, Any],
        previous_emails: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Exception]]:
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
                "product_context": lead.get("_product_context"),
                "sender_name": lead["sender_name"],
                "sender_email": lead["sender_email"],
                "current_sequence": lead["current_sequence"] + 1,
                "max_follow_ups": lead["max_follow_ups"],
            }

            recent_emails = previous_emails[-5:] if len(previous_emails) > 5 else previous_emails
            personalized = await MailAgentUtility.generate_mail(user_info, campaign_info, recent_emails)

            email_data = {
                "lead_id": lead_id,
                "lead": lead,
                "subject": personalized.subject,
                "body": personalized.body,
                "sequence_number": lead["current_sequence"] + 1,
            }

            return (lead, email_data, None)

        except Exception as e:
            return (lead, None, e)

    @staticmethod
    async def process_leads_job() -> None:
        work_done = False
        try:
            leads = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.get_eligible_leads)
            if not leads:
                return

            user_ids = list({str(lead["user_id"]) for lead in leads})
            user_daily_counts: Dict[str, int] = {}
            for uid in user_ids:
                user_daily_counts[uid] = await SchedulerProcessorUtility.run_sync(MailClientUtility.get_daily_send_count, uid)

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
                return

            leads = leads_within_limit

            lead_ids = [str(lead["lead_id"]) for lead in leads]
            locked_ids = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.lock_leads, lead_ids)

            if not locked_ids:
                return

            locked_leads = [l for l in leads if str(l["lead_id"]) in locked_ids]

            previous_emails_map = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.get_previous_emails_batch, locked_ids)
            unique_campaign_ids = list({str(l["campaign_id"]) for l in locked_leads})
            product_context_map = await SchedulerProcessorUtility.run_sync(
                SchedulerQueryUtility.get_product_context_by_campaign, unique_campaign_ids
            )

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

            async def generate_with_semaphore(lead: Dict[str, Any]) -> Any:
                async with semaphore:
                    prev_emails = previous_emails_map.get(str(lead["lead_id"]), [])
                    lead["_product_context"] = product_context_map.get(str(lead["campaign_id"]))
                    return await SchedulerProcessorUtility.generate_email_for_lead(lead, prev_emails)

            generation_results = await asyncio.gather(
                *[generate_with_semaphore(lead) for lead in locked_leads],
                return_exceptions=True,
            )

            successful_generations: List[Dict[str, Any]] = []
            failed_leads: List[Dict[str, Any]] = []

            for result in generation_results:
                if isinstance(result, BaseException):
                    continue
                lead, email_data, error = result
                if error or email_data is None:
                    failed_leads.append(lead)
                else:
                    successful_generations.append(email_data)

            if failed_leads:
                await SchedulerProcessorUtility.run_sync(
                    SchedulerQueryUtility.handle_generation_failures, failed_leads, "Email generation failed"
                )

            if not successful_generations:
                return

            campaign_ids = list(
                {gen["lead"]["campaign_id"] for gen in successful_generations}
            )
            rate_limits = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.get_campaign_rate_limits, campaign_ids)

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

            if skipped_leads:
                skipped_ids = [str(l["lead_id"]) for l in skipped_leads]
                with DatabaseEngine.get_cursor(commit=True) as cur:
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

            gen_lead_ids = [str(gen["lead"]["lead_id"]) for gen in successful_generations]
            replied_ids = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.check_replied_leads, gen_lead_ids)

            if replied_ids:
                successful_generations = [
                    gen
                    for gen in successful_generations
                    if str(gen["lead"]["lead_id"]) not in replied_ids
                ]
                with DatabaseEngine.get_cursor(commit=True) as cur:
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
                user_email_for_check = gens[0]["lead"]["sender_email"]
                lead_email_to_id_map = {g["lead"]["email"].lower(): g["lead_id"] for g in gens}

                try:
                    earliest_sent_map = SchedulerQueryUtility.get_lead_earliest_sent_map(
                        list(lead_email_to_id_map.values())
                    )
                    just_replied = await SchedulerProcessorUtility.run_sync(
                        ImapUtility.check_replies_for_leads,
                        uid,
                        user_email_for_check,
                        lead_email_to_id_map,
                        earliest_sent_map,
                    )
                    if just_replied:
                        gens = [g for g in gens if g["lead_id"] not in just_replied]
                        if not gens:
                            continue
                except Exception:
                    logger.exception("IMAP pre-send check failed for user %s — proceeding with all leads", uid)

                lead_ids_in_group = [gen["lead_id"] for gen in gens]
                last_message_ids: Dict[str, Optional[str]] = {}
                original_subjects: Dict[str, str] = {}
                with DatabaseEngine.get_cursor() as cur:
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

                mails_to_send = []
                for gen in gens:
                    lead = gen["lead"]
                    lead_id = gen["lead_id"]

                    subject = gen["subject"]
                    if lead_id in original_subjects and gen["sequence_number"] > 1:
                        orig = original_subjects[lead_id]
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
                    send_results = await SchedulerProcessorUtility.run_sync(MailClientUtility.send_mails_sequential, mails_to_send, uid)

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
                except Exception:
                    logger.exception("Batch send failed for user %s — marking all %d leads as failed", uid, len(gens))
                    all_send_failures.extend([g["lead"] for g in gens])

            if all_email_records:
                await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.record_emails_batch, all_email_records)
            if all_lead_updates:
                await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.update_leads_after_send, all_lead_updates)
            if all_send_failures:
                await SchedulerProcessorUtility.run_sync(
                    SchedulerQueryUtility.handle_generation_failures,
                    all_send_failures,
                    "Gmail send failed",
                )

            all_campaign_ids = list(
                {gen["lead"]["campaign_id"] for gen in successful_generations}
            )
            work_done = True
            await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.check_campaign_completion, all_campaign_ids)

        except Exception:
            logger.exception("process_leads_job failed — job will retry on next tick")
        finally:
            if work_done:
                await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.check_all_active_campaigns_completion)

    @staticmethod
    async def check_replies_job() -> None:
        try:
            with DatabaseEngine.get_cursor() as cur:
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

            for user in users:
                uid = str(user["user_id"])
                user_email = user["user_email"]

                try:
                    replies = await SchedulerProcessorUtility.run_sync(ImapUtility.check_replies_for_user, uid, user_email)

                    for reply in replies:
                        reply_body = ReplyUtility.extract_reply_text(reply.get("body", ""))
                        ReplyUtility.mark_lead_replied(
                            lead_id=reply["lead_id"],
                            subject=reply.get("subject", ""),
                            reply_content=reply_body or "(Reply content unavailable)",
                            gmail_message_id=reply.get("gmail_message_id"),
                            received_at=reply.get("received_at"),
                        )

                    if replies:
                        campaign_ids: list[str] = []
                        with DatabaseEngine.get_cursor() as cur:
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
                            SchedulerQueryUtility.check_campaign_completion(campaign_ids)

                except Exception:
                    logger.exception("IMAP reply check failed for user %s", uid)
                    continue

        except Exception:
            logger.exception("check_replies_job failed — job will retry on next tick")

    @staticmethod
    async def check_scheduled_campaigns() -> None:
        try:
            with DatabaseEngine.get_cursor(commit=True) as cur:
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

                    cur.execute("SELECT COUNT(*) as count FROM leads WHERE campaign_id = %s", (cid,))
                    if cur.fetchone()["count"] == 0:
                        continue

                    cur.execute(
                        "UPDATE campaigns SET status = 'active', updated_at = NOW() WHERE id = %s",
                        (cid,),
                    )

                    cur.execute(
                        """
                        UPDATE leads
                        SET next_email_at = NOW(), updated_at = NOW()
                        WHERE campaign_id = %s AND status = 'pending' AND next_email_at IS NULL
                        """,
                        (cid,),
                    )
        except Exception:
            logger.exception("check_scheduled_campaigns failed — job will retry on next tick")