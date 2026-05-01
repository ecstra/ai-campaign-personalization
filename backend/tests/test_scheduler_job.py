"""Tests for scheduler async jobs: process_leads_job and check_replies_job with mocked externals."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.db.engine import get_cursor
from src.mail.base import PersonalizedMessage
from src.scheduler.job import process_leads_job, check_replies_job
from conftest import insert_user, insert_campaign, insert_lead, insert_email


def _mock_generate_mail():
    """Create an AsyncMock that returns a PersonalizedMessage."""
    mock = AsyncMock()
    mock.return_value = PersonalizedMessage(
        subject="Test Subject",
        body="<p>Test email body</p>",
    )
    return mock


def _mock_send_gmail():
    """Create a Mock that returns a fake Message-ID."""
    mock = MagicMock()
    mock.return_value = "<test-msg-id@gmail.com>"
    return mock


# ── Happy Path ──────────────────────────────────────────────────────────────


class TestProcessLeadsJob:
    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    @patch("src.mail.client.send_gmail")
    async def test_full_cycle(self, mock_smtp, mock_llm):
        mock_llm.side_effect = _mock_generate_mail()
        mock_smtp.side_effect = _mock_send_gmail()

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead1 = insert_lead(campaign_id=campaign["id"], email="a@test.com")
        lead2 = insert_lead(campaign_id=campaign["id"], email="b@test.com")

        await process_leads_job()

        # Verify emails recorded
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM emails WHERE status = 'sent'")
            assert cur.fetchone()["count"] == 2

            # Verify leads updated
            cur.execute(
                "SELECT status, current_sequence, locked_at FROM leads WHERE id IN (%s, %s)",
                (lead1["id"], lead2["id"]),
            )
            rows = cur.fetchall()
            for row in rows:
                assert row["status"] == "active"
                assert row["current_sequence"] == 1
                assert row["locked_at"] is None

    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    @patch("src.mail.client.send_gmail")
    async def test_sets_threading(self, mock_smtp, mock_llm):
        mock_llm.side_effect = _mock_generate_mail()
        mock_smtp.side_effect = _mock_send_gmail()

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(
            campaign_id=campaign["id"],
            current_sequence=1,
            status="pending",
        )
        # Existing sent email with a message_id
        insert_email(
            lead_id=lead["id"],
            sequence_number=1,
            message_id="<original-msg@gmail.com>",
        )

        await process_leads_job()

        with get_cursor() as cur:
            cur.execute(
                """
                SELECT in_reply_to FROM emails
                WHERE lead_id = %s AND sequence_number = 2
                """,
                (lead["id"],),
            )
            new_email = cur.fetchone()
            assert new_email is not None
            assert new_email["in_reply_to"] == "<original-msg@gmail.com>"


# ── Failure Paths ───────────────────────────────────────────────────────────


class TestProcessLeadsFailures:
    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    async def test_generation_failure_retries_lead(self, mock_llm):
        mock_llm.side_effect = AsyncMock(side_effect=RuntimeError("LLM down"))

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active", max_follow_ups=3)
        lead = insert_lead(campaign_id=campaign["id"], current_sequence=0)

        await process_leads_job()

        with get_cursor() as cur:
            cur.execute(
                "SELECT status, current_sequence, locked_at FROM leads WHERE id = %s",
                (lead["id"],),
            )
            row = cur.fetchone()
            assert row["status"] == "pending"  # Retryable, not terminal
            assert row["current_sequence"] == 1
            assert row["locked_at"] is None  # Unlocked for retry

    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    @patch("src.mail.client.send_gmail")
    async def test_send_failure_records_error(self, mock_smtp, mock_llm):
        mock_llm.side_effect = _mock_generate_mail()
        mock_smtp.side_effect = MagicMock(side_effect=RuntimeError("SMTP connection refused"))

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(campaign_id=campaign["id"])

        await process_leads_job()

        # Lead should not be stuck in processing
        with get_cursor() as cur:
            cur.execute("SELECT status, locked_at FROM leads WHERE id = %s", (lead["id"],))
            row = cur.fetchone()
            assert row["status"] != "processing"
            assert row["locked_at"] is None


# ── Rate Limiting ───────────────────────────────────────────────────────────


class TestProcessLeadsRateLimiting:
    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    @patch("src.mail.client.send_gmail")
    async def test_daily_limit_skips_excess(self, mock_smtp, mock_llm):
        mock_llm.side_effect = _mock_generate_mail()
        mock_smtp.side_effect = _mock_send_gmail()

        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")

        # Pre-fill 449 sent emails (limit is 450)
        filler_lead = insert_lead(
            campaign_id=campaign["id"],
            email="filler@test.com",
            status="active",
            current_sequence=449,
            next_email_at="NOW() + INTERVAL '1 day'",
        )
        for i in range(449):
            insert_email(lead_id=filler_lead["id"], sequence_number=i + 1)

        # Add 3 eligible leads
        for i in range(3):
            insert_lead(campaign_id=campaign["id"], email=f"new{i}@test.com")

        await process_leads_job()

        # At most 1 should have been sent (450 - 449 = 1)
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) as count FROM emails
                WHERE status = 'sent'
                  AND lead_id IN (
                      SELECT id FROM leads WHERE email LIKE 'new%@test.com'
                  )
                """,
            )
            assert cur.fetchone()["count"] <= 1


# ── Multi-user ──────────────────────────────────────────────────────────────


class TestProcessLeadsMultiUser:
    @pytest.mark.asyncio
    @patch("src.scheduler.job.generate_mail")
    @patch("src.mail.client.send_gmail")
    async def test_processes_both_users(self, mock_smtp, mock_llm):
        mock_llm.side_effect = _mock_generate_mail()
        mock_smtp.side_effect = _mock_send_gmail()

        user1 = insert_user(google_id="u1", email="user1@gmail.com", name="User One")
        user2 = insert_user(google_id="u2", email="user2@gmail.com", name="User Two")

        c1 = insert_campaign(user_id=user1["id"], sender_email=user1["email"])
        c2 = insert_campaign(user_id=user2["id"], sender_email=user2["email"])

        insert_lead(campaign_id=c1["id"], email="lead-u1@test.com")
        insert_lead(campaign_id=c2["id"], email="lead-u2@test.com")

        await process_leads_job()

        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM emails WHERE status = 'sent'")
            assert cur.fetchone()["count"] == 2


# ── Reply Checking Job ──────────────────────────────────────────────────────


class TestCheckRepliesJob:
    @pytest.mark.asyncio
    @patch("src.scheduler.job.check_replies_for_user")
    async def test_processes_replies(self, mock_imap):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(
            campaign_id=campaign["id"],
            status="active",
            has_replied=False,
        )
        insert_email(lead_id=lead["id"], sequence_number=1, message_id="<sent@gmail.com>")

        mock_imap.return_value = [{
            "lead_id": lead["id"],
            "subject": "Re: Hello",
            "body": "Thanks for reaching out!",
            "gmail_message_id": "<reply@gmail.com>",
        }]

        await check_replies_job()

        with get_cursor() as cur:
            cur.execute("SELECT has_replied, status FROM leads WHERE id = %s", (lead["id"],))
            row = cur.fetchone()
            assert row["has_replied"] is True
            assert row["status"] == "replied"

    @pytest.mark.asyncio
    @patch("src.scheduler.job.check_replies_for_user")
    async def test_triggers_campaign_completion(self, mock_imap):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        # Only one lead, and it will reply
        lead = insert_lead(
            campaign_id=campaign["id"],
            status="active",
            has_replied=False,
        )
        insert_email(lead_id=lead["id"], sequence_number=1)

        mock_imap.return_value = [{
            "lead_id": lead["id"],
            "subject": "Re: Hello",
            "body": "Interested!",
            "gmail_message_id": "<reply@gmail.com>",
        }]

        await check_replies_job()

        with get_cursor() as cur:
            cur.execute("SELECT status FROM campaigns WHERE id = %s", (campaign["id"],))
            assert cur.fetchone()["status"] == "completed"
