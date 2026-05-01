"""Tests for mail client: daily send counting, idempotency, sequential sending."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.mail.client import get_daily_send_count, check_already_sent, send_mails_sequential
from src.mail.base import Mail, Sender
from conftest import insert_user, insert_campaign, insert_lead, insert_email


class TestDailySendCount:
    def test_zero_when_no_emails(self):
        user = insert_user()
        assert get_daily_send_count(user["id"]) == 0

    def test_counts_recent_sent_emails(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        for seq in range(1, 6):
            insert_email(lead_id=lead["id"], sequence_number=seq, status="sent")
        assert get_daily_send_count(user["id"]) == 5

    def test_excludes_old_emails(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])

        # 3 old emails (25 hours ago)
        old_time = f"'{(datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()}'::timestamptz"
        for seq in range(1, 4):
            insert_email(lead_id=lead["id"], sequence_number=seq, sent_at=old_time)

        # 2 recent emails
        insert_email(lead_id=lead["id"], sequence_number=4, status="sent")
        insert_email(lead_id=lead["id"], sequence_number=5, status="sent")

        assert get_daily_send_count(user["id"]) == 2

    def test_excludes_failed_emails(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])

        insert_email(lead_id=lead["id"], sequence_number=1, status="sent")
        insert_email(lead_id=lead["id"], sequence_number=2, status="sent")
        insert_email(lead_id=lead["id"], sequence_number=3, status="sent")
        insert_email(lead_id=lead["id"], sequence_number=4, status="failed")
        insert_email(lead_id=lead["id"], sequence_number=5, status="failed")

        assert get_daily_send_count(user["id"]) == 3


class TestIdempotency:
    def test_already_sent_true(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        insert_email(lead_id=lead["id"], sequence_number=1, status="sent")
        assert check_already_sent(lead["id"], 1) is True

    def test_already_sent_false(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        assert check_already_sent(lead["id"], 2) is False

    def test_failed_email_not_counted(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        insert_email(lead_id=lead["id"], sequence_number=1, status="failed")
        assert check_already_sent(lead["id"], 1) is False


class TestSequentialSend:
    @patch("src.mail.client.send_gmail")
    def test_calls_gmail_for_each_mail(self, mock_send_gmail):
        mock_send_gmail.return_value = "<msg-test@gmail.com>"

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])

        mails = []
        for i in range(3):
            lead = insert_lead(
                campaign_id=campaign["id"],
                email=f"lead{i}@test.com",
                first_name=f"Lead{i}",
                last_name="Test",
            )
            mails.append({
                "mail": Mail(
                    sender=Sender(name="Test", email=user["email"]),
                    to=f"lead{i}@test.com",
                    subject=f"Subject {i}",
                    body=f"<p>Body {i}</p>",
                ),
                "lead_id": lead["id"],
                "sequence_number": 1,
                "in_reply_to": None,
            })

        results = send_mails_sequential(mails, user["id"])
        assert len(results) == 3
        assert all(r["status"] == "sent" for r in results)
        assert all(r["message_id"] == "<msg-test@gmail.com>" for r in results)
        assert mock_send_gmail.call_count == 3
