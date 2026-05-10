import os
import time

from ..base import Mail
from .gmail import GmailUtility
from src.db import DatabaseEngine

INTER_SEND_DELAY_MS = int(os.getenv("GMAIL_INTER_SEND_DELAY_MS", "200"))
GMAIL_DAILY_SEND_LIMIT = int(os.getenv("GMAIL_DAILY_SEND_LIMIT", "450"))

class MailClientUtility:

    @staticmethod
    def get_daily_send_count(user_id: str) -> int:
        with DatabaseEngine.get_cursor() as cur:
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

    @staticmethod
    def check_already_sent(lead_id: str, sequence_number: int) -> bool:
        with DatabaseEngine.get_cursor() as cur:
            cur.execute(
                """
                SELECT id FROM emails
                WHERE lead_id = %s AND sequence_number = %s AND status = 'sent'
                """,
                (lead_id, sequence_number),
            )
            return cur.fetchone() is not None

    @staticmethod
    def send_mail(
        mail: Mail,
        user_id: str,
        lead_id: str,
        sequence_number: int,
        in_reply_to: str | None = None,
    ) -> str | None:
        if MailClientUtility.check_already_sent(lead_id, sequence_number):
            return None

        return GmailUtility.send_gmail(
            user_id=user_id,
            from_email=mail.sender.email,
            from_name=mail.sender.name,
            to_email=mail.to,
            subject=mail.subject,
            html_body=mail.body,
            in_reply_to=in_reply_to,
        )

    @staticmethod
    def send_mails_sequential(mails: list[dict], user_id: str) -> list[dict]:
        results: list[dict] = []

        for i, item in enumerate(mails):
            mail: Mail = item["mail"]
            lead_id: str = item["lead_id"]
            sequence_number: int = item["sequence_number"]
            in_reply_to: str | None = item.get("in_reply_to")

            try:
                message_id = MailClientUtility.send_mail(
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
                results.append({
                    "lead_id": lead_id,
                    "sequence_number": sequence_number,
                    "message_id": None,
                    "status": "failed",
                    "error": str(e),
                })

            if i < len(mails) - 1:
                time.sleep(INTER_SEND_DELAY_MS / 1000)

        return results