import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formataddr, formatdate
from typing import Optional

from core.auth import TokenUtility
from ._xoauth2 import build_xoauth2_smtp

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

class GmailUtility:

    @staticmethod
    def send_gmail(
        user_id: str,
        from_email: str,
        from_name: str,
        to_email: str,
        subject: str,
        html_body: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        _, _, domain = from_email.partition("@")
        if not domain:
            raise ValueError(f"Invalid from_email address: {from_email!r}")

        message_id = make_msgid(domain=domain)

        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg["Date"] = formatdate(localtime=True)

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to

        msg.attach(MIMEText(html_body, "html"))

        last_exception: Optional[Exception] = None
        token_refreshed = False

        for attempt in range(MAX_RETRIES):
            try:
                access_token = TokenUtility.get_valid_access_token(user_id)
                auth_string = build_xoauth2_smtp(from_email, access_token)

                with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.docmd("AUTH", f"XOAUTH2 {auth_string}")
                    smtp.sendmail(from_email, [to_email], msg.as_string())

                return message_id

            except smtplib.SMTPAuthenticationError as e:
                if not token_refreshed:
                    try:
                        TokenUtility.refresh_access_token(user_id)
                        token_refreshed = True
                        continue
                    except Exception as refresh_err:
                        logger.exception("Token refresh failed during SMTP auth retry for user %s", user_id)
                        raise refresh_err from e
                raise

            except Exception as e:
                last_exception = e

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])

        raise last_exception  # type: ignore[misc]