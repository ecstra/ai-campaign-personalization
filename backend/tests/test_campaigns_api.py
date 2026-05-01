"""Tests for campaign API endpoints: CRUD, status transitions, multi-tenancy, stats."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db.engine import get_cursor
from conftest import insert_campaign, insert_lead, insert_email


class TestCampaignCRUD:
    def test_create_campaign(self, client, test_user):
        resp = client.post("/campaigns", json={
            "name": "Q1 Outreach",
            "sender_name": "John",
            "goal": "Book demo calls",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Q1 Outreach"
        assert data["sender_email"] == test_user["email"]
        assert data["user_id"] == test_user["id"]
        assert data["status"] == "draft"

    def test_create_campaign_missing_goal(self, client):
        resp = client.post("/campaigns", json={
            "name": "No Goal Campaign",
            "sender_name": "John",
        })
        assert resp.status_code == 422

    def test_create_campaign_with_empty_scheduled_start_at(self, client, test_user):
        """
        Regression: the frontend sends scheduled_start_at="" when the date
        picker is untouched. Postgres cannot coerce that to TIMESTAMPTZ, so
        the backend must normalise empty strings to NULL before inserting.
        """
        resp = client.post("/campaigns", json={
            "name": "Untouched Schedule",
            "sender_name": "John",
            "goal": "test",
            "scheduled_start_at": "",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["scheduled_start_at"] is None

    def test_create_campaign_with_valid_scheduled_start_at(self, client, test_user):
        """When the date picker IS used, the value should round-trip correctly."""
        scheduled = "2026-12-01T09:00:00+00:00"
        resp = client.post("/campaigns", json={
            "name": "Scheduled Campaign",
            "sender_name": "John",
            "goal": "test",
            "scheduled_start_at": scheduled,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["scheduled_start_at"] is not None

    def test_list_campaigns_empty(self, client):
        resp = client.get("/campaigns")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_campaigns_returns_only_own(self, client, test_user, second_user):
        insert_campaign(user_id=test_user["id"], name="My Campaign 1")
        insert_campaign(user_id=test_user["id"], name="My Campaign 2")
        insert_campaign(user_id=second_user["id"], name="Other User Campaign")

        resp = client.get("/campaigns")
        assert resp.status_code == 200
        campaigns = resp.json()
        assert len(campaigns) == 2
        names = {c["name"] for c in campaigns}
        assert "My Campaign 1" in names
        assert "My Campaign 2" in names
        assert "Other User Campaign" not in names

    def test_get_campaign_own(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        resp = client.get(f"/campaigns/{campaign['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == campaign["id"]

    def test_get_campaign_other_user_returns_404(self, client, second_user):
        other_campaign = insert_campaign(user_id=second_user["id"])
        resp = client.get(f"/campaigns/{other_campaign['id']}")
        assert resp.status_code == 404

    def test_delete_campaign(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        resp = client.delete(f"/campaigns/{campaign['id']}")
        assert resp.status_code == 200

        resp = client.get(f"/campaigns/{campaign['id']}")
        assert resp.status_code == 404

    def test_delete_campaign_other_user_returns_404(self, client, second_user):
        other_campaign = insert_campaign(user_id=second_user["id"])
        resp = client.delete(f"/campaigns/{other_campaign['id']}")
        assert resp.status_code == 404

        # Verify campaign still exists
        with get_cursor() as cur:
            cur.execute("SELECT id FROM campaigns WHERE id = %s", (other_campaign["id"],))
            assert cur.fetchone() is not None


class TestCampaignStatusTransitions:
    def test_start_campaign_with_leads(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        insert_lead(campaign_id=campaign["id"], email="a@b.com")
        insert_lead(campaign_id=campaign["id"], email="c@d.com")

        resp = client.patch(f"/campaigns/{campaign['id']}/status?action=start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        # Verify leads got next_email_at set
        with get_cursor() as cur:
            cur.execute(
                "SELECT next_email_at FROM leads WHERE campaign_id = %s",
                (campaign["id"],),
            )
            leads = cur.fetchall()
            assert all(l["next_email_at"] is not None for l in leads)

    def test_start_campaign_no_leads_returns_400(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        resp = client.patch(f"/campaigns/{campaign['id']}/status?action=start")
        assert resp.status_code == 400
        assert "no leads" in resp.json()["detail"].lower()

    def test_start_completed_campaign_returns_400(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="completed")
        resp = client.patch(f"/campaigns/{campaign['id']}/status?action=start")
        assert resp.status_code == 400

    def test_stop_active_campaign(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="active")
        resp = client.patch(f"/campaigns/{campaign['id']}/status?action=stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"


class TestCampaignStats:
    def test_campaign_stats_counts(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        lead1 = insert_lead(campaign_id=campaign["id"], email="a@b.com")
        lead2 = insert_lead(campaign_id=campaign["id"], email="c@d.com")
        lead3 = insert_lead(campaign_id=campaign["id"], email="e@f.com")

        # 3 emails in rate window (recent)
        insert_email(lead_id=lead1["id"], sequence_number=1)
        insert_email(lead_id=lead2["id"], sequence_number=1)
        insert_email(lead_id=lead3["id"], sequence_number=1)

        # 2 emails outside rate window (old)
        old_time = f"'{(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}'::timestamptz"
        insert_email(lead_id=lead1["id"], sequence_number=2, sent_at=old_time)
        insert_email(lead_id=lead2["id"], sequence_number=2, sent_at=old_time)

        resp = client.get(f"/campaigns/{campaign['id']}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["emails_sent"] == 5
        assert stats["emails_in_window"] == 3
        assert stats["rate_limit_remaining"] == 47
