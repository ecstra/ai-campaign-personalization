"""Gmail SMTP sending via XOAUTH2 authentication."""

import base64
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formataddr, formatdate
from typing import Optional

from ..auth.tokens import get_valid_access_token
from ..logger import logger

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]


def _build_xoauth2_string(user_email: str, access_token: str) -> str:
    """Build the XOAUTH2 authentication string for SMTP."""
    auth_string = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth_string.encode()).decode()


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
    """
    Send a single email via Gmail SMTP using XOAUTH2.

    Returns:
        The Message-ID of the sent email (RFC 2822 format).

    Raises:
        smtplib.SMTPException or ValueError on failure after retries.
    """
    message_id = make_msgid(domain=from_email.split("@")[1])

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
            access_token = get_valid_access_token(user_id)
            auth_string = _build_xoauth2_string(from_email, access_token)

            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.docmd("AUTH", f"XOAUTH2 {auth_string}")
                smtp.sendmail(from_email, [to_email], msg.as_string())

            logger.info(f"Email sent to {to_email} via Gmail SMTP (message_id={message_id})")
            return message_id

        except smtplib.SMTPAuthenticationError as e:
            # Token may have expired between validation and use. Try one refresh.
            if not token_refreshed:
                logger.warning(f"SMTP auth failed for {from_email}, refreshing token (attempt {attempt + 1})")
                from ..auth.tokens import refresh_access_token
                try:
                    refresh_access_token(user_id)
                    token_refreshed = True
                    continue
                except ValueError:
                    last_exception = e
                    break
            last_exception = e

        except Exception as e:
            last_exception = e
            logger.warning(
                f"Gmail send to {to_email} failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
            )

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAYS[attempt])

    logger.error(f"Gmail send failed after {MAX_RETRIES} attempts to {to_email}: {last_exception}")
    raise last_exception or RuntimeError("Send failed with no captured exception")
