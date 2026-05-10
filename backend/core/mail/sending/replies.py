import re
from datetime import datetime

from src.db import DatabaseEngine

class ReplyUtility:

    @staticmethod
    def extract_reply_html(html: str) -> str:
        if not html:
            return ""

        quote_patterns = [
            r'<div[^>]*class="[^"]*gmail_quote[^"]*".*',
            r'<div[^>]*class="[^"]*yahoo_quoted[^"]*".*',
            r'<blockquote.*',
            r'<div[^>]*id="appendonsend".*',
            r'<div[^>]*id="divRplyFwdMsg".*',
            r'<hr[^>]*>.*On .* wrote:.*',
            r'<div[^>]*>On .* wrote:.*',
            r'-{3,}\s*Original Message\s*-{3,}.*',
            r'_{3,}\s*From:.*',
        ]

        result = html
        for pattern in quote_patterns:
            result = re.split(pattern, result, flags=re.IGNORECASE | re.DOTALL)[0]

        return result.strip()

    @staticmethod
    def extract_reply_text(text: str) -> str:
        if not text:
            return ""

        lines = text.splitlines()
        reply_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(">"):
                break
            if re.match(r"^On .+ wrote:$", stripped):
                break
            if re.match(r"^-{3,}\s*Original Message", stripped, re.IGNORECASE):
                break
            if re.match(r"^_{3,}\s*From:", stripped, re.IGNORECASE):
                break
            reply_lines.append(line)

        return "\n".join(reply_lines).strip()

    @staticmethod
    def mark_lead_replied(
        lead_id: str,
        subject: str,
        reply_content: str,
        gmail_message_id: str | None = None,
        received_at: datetime | None = None,
    ) -> bool:
        try:
            with DatabaseEngine.get_cursor(commit=True) as cur:
                cur.execute(
                    "SELECT id, campaign_id, has_replied FROM leads WHERE id = %s",
                    (lead_id,),
                )
                lead = cur.fetchone()
                if not lead:
                    return False

                if lead["has_replied"]:
                    return True

                cur.execute(
                    """
                    UPDATE leads
                    SET has_replied = true,
                        status = 'replied',
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (lead_id,),
                )

                cur.execute(
                    """
                    INSERT INTO emails (lead_id, sequence_number, subject, body, status, message_id, sent_at)
                    VALUES (%s, 0, %s, %s, 'received', %s, COALESCE(%s, NOW()))
                    """,
                    (lead_id, f"[REPLY] {subject}", reply_content, gmail_message_id, received_at),
                )

                return True

        except Exception:
            return False
