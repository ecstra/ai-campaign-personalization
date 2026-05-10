import asyncio
import functools
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from src.db import DatabaseEngine
from core.mail import MailAgentUtility, MailClientUtility, Mail, Sender
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
        lead: dict[str, Any],
        previous_emails: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, Exception | None]:
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

            lead_ids = [str(lead["lead_id"]) for lead in leads]
            locked_ids = await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.lock_leads, lead_ids)

            if not locked_ids:
                return

            locked_leads = [lead_item for lead_item in leads if str(lead_item["lead_id"]) in locked_ids]

            previous_emails_map = await SchedulerProcessorUtility.run_sync(
                SchedulerQueryUtility.get_previous_emails_batch, locked_ids
            )
            unique_campaign_ids = list({str(lead_item["campaign_id"]) for lead_item in locked_leads})
            product_context_map = await SchedulerProcessorUtility.run_sync(
                SchedulerQueryUtility.get_product_context_by_campaign, unique_campaign_ids
            )

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

            async def generate_with_semaphore(lead: dict[str, Any]) -> Any:
                async with semaphore:
                    prev_emails = previous_emails_map.get(str(lead["lead_id"]), [])
                    lead["_product_context"] = product_context_map.get(str(lead["campaign_id"]))
                    return await SchedulerProcessorUtility.generate_email_for_lead(lead, prev_emails)

            generation_results = await asyncio.gather(
                *[generate_with_semaphore(lead) for lead in locked_leads],
                return_exceptions=True,
            )

            successful_generations: list[dict[str, Any]] = []
            failed_leads: list[dict[str, Any]] = []

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

            campaign_ids = list({gen["lead"]["campaign_id"] for gen in successful_generations})
            rate_limits = await SchedulerProcessorUtility.run_sync(
                SchedulerQueryUtility.get_campaign_rate_limits, campaign_ids
            )

            campaign_gens: dict[str, list[dict[str, Any]]] = {}
            for gen in successful_generations:
                cid = gen["lead"]["campaign_id"]
                campaign_gens.setdefault(cid, []).append(gen)

            filtered_generations: list[dict[str, Any]] = []
            skipped_leads: list[dict[str, Any]] = []

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
                skipped_ids = [str(lead_item["lead_id"]) for lead_item in skipped_leads]
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
            replied_ids = await SchedulerProcessorUtility.run_sync(
                SchedulerQueryUtility.check_replied_leads, gen_lead_ids
            )

            if replied_ids:
                successful_generations = [
                    gen for gen in successful_generations
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

            original_subjects: dict[str, str] = {}
            last_message_ids: dict[str, str | None] = {}
            with DatabaseEngine.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (lead_id) lead_id, message_id
                    FROM emails
                    WHERE lead_id = ANY(%s::uuid[]) AND status = 'sent' AND message_id IS NOT NULL
                    ORDER BY lead_id, sequence_number DESC
                    """,
                    (gen_lead_ids,),
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
                    (gen_lead_ids,),
                )
                for row in cur.fetchall():
                    original_subjects[str(row["lead_id"])] = row["subject"]

            mails: list[Mail] = []
            lead_id_map: dict[str, dict[str, Any]] = {}
            for gen in successful_generations:
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
                    lead_id=lead_id,
                )
                mails.append(mail)
                lead_id_map[lead_id] = {
                    "lead": lead,
                    "sequence_number": gen["sequence_number"],
                    "subject": gen["subject"],
                    "body": gen["body"],
                    "in_reply_to": last_message_ids.get(lead_id),
                }

            idempotency_key = hashlib.sha256(
                ",".join(sorted(f"{lid}-{lead_id_map[lid]['sequence_number']}" for lid in lead_id_map)).encode()
            ).hexdigest()

            try:
                MailClientUtility.send_mail_batch(mails, idempotency_key)
            except Exception:
                logger.exception("Batch send failed — marking all %d leads as failed", len(mails))
                await SchedulerProcessorUtility.run_sync(
                    SchedulerQueryUtility.handle_generation_failures,
                    [lead_id_map[lid]["lead"] for lid in lead_id_map],
                    "Batch send failed",
                )
                return

            now = datetime.now(timezone.utc)
            all_email_records: list[dict[str, Any]] = []
            all_lead_updates: list[dict[str, Any]] = []

            for lead_id, info in lead_id_map.items():
                all_email_records.append({
                    "lead_id": lead_id,
                    "sequence_number": info["sequence_number"],
                    "subject": info["subject"],
                    "body": info["body"],
                    "status": "sent",
                    "message_id": None,
                    "in_reply_to": info["in_reply_to"],
                    "sent_at": now,
                })
                all_lead_updates.append({
                    "lead_id": lead_id,
                    "new_sequence": info["sequence_number"],
                    "max_follow_ups": info["lead"]["max_follow_ups"],
                    "follow_up_delay_minutes": info["lead"]["follow_up_delay_minutes"],
                })

            await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.record_emails_batch, all_email_records)
            await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.update_leads_after_send, all_lead_updates)

            all_campaign_ids = list({info["lead"]["campaign_id"] for info in lead_id_map.values()})
            work_done = True
            await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.check_campaign_completion, all_campaign_ids)

        except Exception:
            logger.exception("process_leads_job failed — job will retry on next tick")
        finally:
            if work_done:
                await SchedulerProcessorUtility.run_sync(SchedulerQueryUtility.check_all_active_campaigns_completion)
