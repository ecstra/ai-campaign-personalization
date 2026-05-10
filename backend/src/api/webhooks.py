import logging
import os
import re

import resend
from fastapi import APIRouter, HTTPException, Request
from svix.webhooks import Webhook, WebhookVerificationError

from ..db import DatabaseEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET")
if not RESEND_WEBHOOK_SECRET:
    raise ValueError("RESEND_WEBHOOK_SECRET environment variable is not set")

def _extract_reply_html(html: str) -> str:
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


def _extract_reply_text(text: str) -> str:
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


def _parse_tracking_email(email: str) -> str | None:
    lead_id = email.split("@")[0]
    if len(lead_id) != 36:
        return None
    return lead_id


def _verify_webhook(payload: bytes, headers: dict, secret: str) -> dict:
    wh = Webhook(secret)
    try:
        return wh.verify(payload, headers)
    except WebhookVerificationError as e:
        raise HTTPException(status_code=401, detail=f"Invalid webhook signature: {e}")


def _mark_lead_replied(lead_id: str, subject: str, reply_content: str) -> bool:
    try:
        with DatabaseEngine.get_cursor(commit=True) as cur:
            cur.execute(
                "SELECT id, campaign_id, has_replied FROM leads WHERE id = %s",
                (lead_id,),
            )
            lead = cur.fetchone()
            if not lead:
                logger.warning("Webhook: lead %s not found", lead_id)
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
                INSERT INTO emails (lead_id, sequence_number, subject, body, status, sent_at)
                VALUES (%s, 0, %s, %s, 'received', NOW())
                """,
                (lead_id, f"[REPLY] {subject}", reply_content),
            )

            campaign_id = lead["campaign_id"]
            cur.execute(
                """
                UPDATE campaigns
                SET status = 'completed', updated_at = NOW()
                WHERE id = %s
                  AND status = 'active'
                  AND NOT EXISTS (
                      SELECT 1 FROM leads l
                      WHERE l.campaign_id = %s
                        AND l.status NOT IN ('completed', 'replied', 'failed')
                  )
                """,
                (campaign_id, campaign_id),
            )

            return True

    except Exception:
        logger.exception("Webhook: failed to mark lead %s as replied", lead_id)
        return False


@router.post("/resend/inbound")
async def handle_resend_inbound(request: Request):
    body = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    payload = _verify_webhook(body, headers, RESEND_WEBHOOK_SECRET)

    event_type = payload.get("type")
    if event_type != "email.received":
        return {"status": "ignored", "reason": f"event type {event_type} not handled"}

    email_data = payload.get("data", {})
    recipients = email_data.get("to", []) + email_data.get("cc", [])

    matched_lead_id = None
    for recipient in recipients:
        parsed = _parse_tracking_email(recipient)
        if parsed:
            matched_lead_id = parsed
            break

    if not matched_lead_id:
        return {"status": "ignored", "reason": "no tracking email found"}

    email_id = email_data.get("email_id")
    try:
        full_email = resend.Emails.Receiving.get(email_id)
        plain = (full_email.get("text") or "").strip()
        html = (full_email.get("html") or "").strip()
        if plain:
            reply_content = _extract_reply_text(plain)
        elif html:
            cleaned = _extract_reply_html(html)
            stripped = re.sub(r"<[^>]+>", "", cleaned)
            reply_content = stripped.strip()
        else:
            reply_content = "(Reply content unavailable)"
    except Exception:
        logger.exception("Webhook: could not fetch full email %s", email_id)
        reply_content = "(Reply content unavailable)"

    subject = email_data.get("subject", "")
    from_addr = email_data.get("from", "")

    success = _mark_lead_replied(matched_lead_id, subject, reply_content)

    if success:
        return {"status": "processed", "lead_id": matched_lead_id, "from": from_addr}
    return {"status": "error", "reason": "failed to mark lead as replied"}
