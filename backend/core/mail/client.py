import os
import re
import time
import resend

from .base import Mail

resend.api_key = os.getenv("RESEND_API_KEY")

EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN")
if not EMAIL_DOMAIN:
    raise ValueError("EMAIL_DOMAIN environment variable is not set")

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

if len(RETRY_DELAYS) != MAX_RETRIES:
    raise ValueError("RETRY_DELAYS must be of length MAX_RETRIES")

def _sanitize(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))

def _build_reply_to(mail: Mail) -> list[str]:
    reply_to = [mail.sender.email]
    if mail.lead_id:
        reply_to.append(f"{mail.lead_id}@{EMAIL_DOMAIN}")
    return reply_to

class MailClientUtility:

    @staticmethod
    def send_mail(mail: Mail) -> resend.Emails.SendResponse:
        params: resend.Emails.SendParams = {
            "from": f"{mail.sender.name} <{_sanitize(mail.sender.name)}@{EMAIL_DOMAIN}>",
            "to": [mail.to],
            "subject": mail.subject,
            "html": mail.body,
            "reply_to": _build_reply_to(mail),
        }

        last_exception: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return resend.Emails.send(params)
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])

        raise last_exception  # type: ignore[misc]

    @staticmethod
    def send_mail_batch(
        mails: list[Mail],
        idempotency_key: str | None = None,
    ) -> list[resend.Emails.SendResponse]:
        params: list[resend.Emails.SendParams] = []
        for mail in mails:
            params.append({
                "from": f"{mail.sender.name} <{_sanitize(mail.sender.name)}@{EMAIL_DOMAIN}>",
                "to": [mail.to],
                "subject": mail.subject,
                "html": mail.body,
                "reply_to": _build_reply_to(mail),
            })

        options: resend.Batch.SendOptions | None = None
        if idempotency_key:
            options = {"idempotency_key": idempotency_key}

        last_exception: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return resend.Batch.send(params, options) if options else resend.Batch.send(params)
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])

        raise last_exception  # type: ignore[misc]
