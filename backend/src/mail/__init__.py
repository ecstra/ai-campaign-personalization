from .agent import generate_mail
from .client import send_mail, send_mails_sequential, get_daily_send_count, GMAIL_DAILY_SEND_LIMIT
from .gmail import send_gmail
from .imap import check_replies_for_user
from .replies import mark_lead_replied, extract_reply_html, extract_reply_text
from .base import Mail, Sender, PersonalizedMessage

__all__ = [
    # Mail Generation (AI)
    "generate_mail",

    # Send Mails (Gmail SMTP)
    "send_mail",
    "send_mails_sequential",
    "send_gmail",

    # Reply Detection (IMAP)
    "check_replies_for_user",

    # Reply Processing
    "mark_lead_replied",
    "extract_reply_html",
    "extract_reply_text",

    # Rate Limiting
    "get_daily_send_count",
    "GMAIL_DAILY_SEND_LIMIT",

    # Data Models
    "PersonalizedMessage",
    "Mail",
    "Sender",
]
