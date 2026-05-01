"""Tests for scheduler database functions: eligible leads, locking, rate limits, completion."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db.engine import get_cursor
from src.scheduler.job import (
    _get_eligible_leads,
    _lock_leads,
    _check_replied_leads,
    _get_campaign_rate_limits,
    _get_previous_emails_batch,
    _record_emails_batch,
    _update_leads_after_send,
    _handle_generation_failures,
    _check_campaign_completion,
    LOCK_TIMEOUT_MINUTES,
    CAMPAIGN_EMAIL_RATE_LIMIT,
    RATE_LIMIT_WINDOW_MINUTES,
)
from conftest import insert_user, insert_campaign, insert_lead, insert_email


# ── Eligible Leads Query ────────────────────────────────────────────────────


class TestEligibleLeads:
    def test_active_campaign_pending_lead(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(campaign_id=campaign["id"], status="pending")

        leads = _get_eligible_leads()
        assert len(leads) == 1
        assert str(leads[0]["lead_id"]) == lead["id"]
        assert str(leads[0]["user_id"]) == user["id"]
        assert leads[0]["user_email"] == user["email"]

    def test_excludes_paused_campaign(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="paused")
        insert_lead(campaign_id=campaign["id"])
        assert len(_get_eligible_leads()) == 0

    def test_excludes_replied_lead(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"], has_replied=True, status="replied")
        assert len(_get_eligible_leads()) == 0

    def test_excludes_completed_lead(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"], status="completed")
        assert len(_get_eligible_leads()) == 0

    def test_excludes_processing_lead(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"], status="processing")
        assert len(_get_eligible_leads()) == 0

    def test_excludes_future_next_email_at(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(
            campaign_id=campaign["id"],
            next_email_at="NOW() + INTERVAL '1 hour'",
        )
        assert len(_get_eligible_leads()) == 0

    def test_respects_max_follow_ups(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active", max_follow_ups=3)
        insert_lead(campaign_id=campaign["id"], current_sequence=3)
        assert len(_get_eligible_leads()) == 0

    def test_rate_limit_full(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        # Create enough leads and sent emails to hit the rate limit
        for i in range(CAMPAIGN_EMAIL_RATE_LIMIT):
            lead = insert_lead(
                campaign_id=campaign["id"],
                email=f"sent{i}@test.com",
                status="active",
                current_sequence=1,
                next_email_at="NOW() + INTERVAL '1 day'",
            )
            insert_email(lead_id=lead["id"], sequence_number=1)

        # Add one more eligible lead
        insert_lead(
            campaign_id=campaign["id"],
            email="eligible@test.com",
            status="pending",
        )
        # Should be excluded because campaign hit rate limit
        assert len(_get_eligible_leads()) == 0

    def test_rate_limit_partial(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        # Fill to 48 out of 50
        for i in range(48):
            lead = insert_lead(
                campaign_id=campaign["id"],
                email=f"sent{i}@test.com",
                status="active",
                current_sequence=1,
                next_email_at="NOW() + INTERVAL '1 day'",
            )
            insert_email(lead_id=lead["id"], sequence_number=1)

        # Add 3 eligible leads
        for i in range(3):
            insert_lead(
                campaign_id=campaign["id"],
                email=f"eligible{i}@test.com",
                status="pending",
            )

        leads = _get_eligible_leads()
        # Only 2 should be returned (50 - 48 = 2 remaining)
        assert len(leads) <= 2

    def test_excludes_user_without_tokens(self):
        user = insert_user(
            google_id="no_tokens",
            email="notokens@gmail.com",
            store_tokens=False,
        )
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"])
        assert len(_get_eligible_leads()) == 0

    def test_stale_lock_recoverable(self):
        """A lead with status='pending' but a stale locked_at should still be eligible.
        This can happen if a previous run crashed after setting locked_at but before
        updating status to 'processing'."""
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(campaign_id=campaign["id"], status="pending")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES + 5)
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE leads SET locked_at = %s WHERE id = %s",
                (stale_time, lead["id"]),
            )
        leads = _get_eligible_leads()
        assert len(leads) == 1

    def test_recent_lock_excluded(self):
        """A lead with status='pending' but a recent locked_at should be excluded
        (another worker is currently processing it)."""
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(campaign_id=campaign["id"], status="pending")
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE leads SET locked_at = NOW() WHERE id = %s",
                (lead["id"],),
            )
        leads = _get_eligible_leads()
        assert len(leads) == 0


# ── Locking ─────────────────────────────────────────────────────────────────


class TestLocking:
    def test_lock_success(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        leads = [
            insert_lead(campaign_id=campaign["id"], email=f"l{i}@test.com")
            for i in range(3)
        ]
        lead_ids = [l["id"] for l in leads]

        locked = _lock_leads(lead_ids)
        assert len(locked) == 3

        # Verify DB state
        with get_cursor() as cur:
            cur.execute(
                "SELECT status, locked_at FROM leads WHERE id = ANY(%s::uuid[])",
                (lead_ids,),
            )
            rows = cur.fetchall()
            assert all(r["status"] == "processing" for r in rows)
            assert all(r["locked_at"] is not None for r in rows)

    def test_already_processing_not_lockable(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(
            campaign_id=campaign["id"],
            status="processing",
            locked_at="NOW()",
        )
        locked = _lock_leads([lead["id"]])
        assert len(locked) == 0

    def test_stale_lock_is_reclaimable(self):
        """A pending lead with a stale locked_at can be re-locked."""
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead = insert_lead(campaign_id=campaign["id"], status="pending")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES + 5)
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE leads SET locked_at = %s WHERE id = %s",
                (stale_time, lead["id"]),
            )
        locked = _lock_leads([lead["id"]])
        assert len(locked) == 1


# ── Failure Handling ────────────────────────────────────────────────────────


class TestFailureHandling:
    def _make_lead_dict(self, lead: dict, campaign: dict) -> dict:
        """Build the dict format that _handle_generation_failures expects."""
        return {
            "lead_id": lead["id"],
            "current_sequence": lead.get("current_sequence", 0),
            "max_follow_ups": campaign.get("max_follow_ups", 3),
            "follow_up_delay_minutes": campaign.get("follow_up_delay_minutes", 2880),
        }

    def test_retryable_failure(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        lead = insert_lead(
            campaign_id=campaign["id"],
            current_sequence=0,
            status="processing",
        )

        lead_dict = self._make_lead_dict(lead, campaign)
        _handle_generation_failures([lead_dict], "LLM timed out")

        with get_cursor() as cur:
            cur.execute("SELECT status, current_sequence, next_email_at FROM leads WHERE id = %s", (lead["id"],))
            row = cur.fetchone()
            assert row["status"] == "pending"
            assert row["current_sequence"] == 1
            assert row["next_email_at"] is not None

            cur.execute(
                "SELECT status, subject FROM emails WHERE lead_id = %s",
                (lead["id"],),
            )
            email = cur.fetchone()
            assert email["status"] == "failed"
            assert "FAILED" in email["subject"]

    def test_terminal_failure(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], max_follow_ups=3)
        lead = insert_lead(
            campaign_id=campaign["id"],
            current_sequence=2,
            status="processing",
        )

        lead_dict = self._make_lead_dict(lead, campaign)
        _handle_generation_failures([lead_dict], "LLM unavailable")

        with get_cursor() as cur:
            cur.execute("SELECT status FROM leads WHERE id = %s", (lead["id"],))
            assert cur.fetchone()["status"] == "failed"


# ── Campaign Completion ─────────────────────────────────────────────────────


class TestCampaignCompletion:
    def test_completes_when_all_terminal(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"], email="a@b.com", status="completed")
        insert_lead(campaign_id=campaign["id"], email="c@d.com", status="replied", has_replied=True)
        insert_lead(campaign_id=campaign["id"], email="e@f.com", status="failed")

        _check_campaign_completion([campaign["id"]])

        with get_cursor() as cur:
            cur.execute("SELECT status FROM campaigns WHERE id = %s", (campaign["id"],))
            assert cur.fetchone()["status"] == "completed"

    def test_stays_active_with_pending_leads(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(campaign_id=campaign["id"], email="a@b.com", status="completed")
        insert_lead(campaign_id=campaign["id"], email="c@d.com", status="active")

        _check_campaign_completion([campaign["id"]])

        with get_cursor() as cur:
            cur.execute("SELECT status FROM campaigns WHERE id = %s", (campaign["id"],))
            assert cur.fetchone()["status"] == "active"


# ── Batch Recording ─────────────────────────────────────────────────────────


class TestBatchRecording:
    def test_record_and_update_batch(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"])
        leads = [
            insert_lead(campaign_id=campaign["id"], email=f"l{i}@t.com")
            for i in range(3)
        ]

        now = datetime.now(timezone.utc)
        email_records = [
            {
                "lead_id": l["id"],
                "sequence_number": 1,
                "subject": f"Subject {i}",
                "body": f"<p>Body {i}</p>",
                "status": "sent",
                "message_id": f"<msg-{i}@gmail.com>",
                "in_reply_to": None,
                "sent_at": now,
            }
            for i, l in enumerate(leads)
        ]
        _record_emails_batch(email_records)

        # Verify emails exist
        with get_cursor() as cur:
            for i, l in enumerate(leads):
                cur.execute(
                    "SELECT message_id, status FROM emails WHERE lead_id = %s",
                    (l["id"],),
                )
                email = cur.fetchone()
                assert email is not None
                assert email["message_id"] == f"<msg-{i}@gmail.com>"
                assert email["status"] == "sent"

        # Now update leads
        lead_updates = [
            {
                "lead_id": l["id"],
                "new_sequence": 1,
                "max_follow_ups": 3,
                "follow_up_delay_minutes": 2880,
            }
            for l in leads
        ]
        _update_leads_after_send(lead_updates)

        with get_cursor() as cur:
            for l in leads:
                cur.execute(
                    "SELECT current_sequence, status, locked_at, next_email_at FROM leads WHERE id = %s",
                    (l["id"],),
                )
                row = cur.fetchone()
                assert row["current_sequence"] == 1
                assert row["status"] == "active"
                assert row["locked_at"] is None
                assert row["next_email_at"] is not None
