"""Tests for lead API endpoints: CRUD, bulk import, ownership, detail, activity."""

import pytest

from src.db.engine import get_cursor
from conftest import insert_campaign, insert_lead, insert_email


class TestLeadCRUD:
    def test_create_lead(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        resp = client.post(f"/campaigns/{campaign['id']}/leads", json={
            "email": "newlead@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "company": "TechCo",
            "title": "CTO",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "newlead@example.com"
        assert data["first_name"] == "Alice"
        assert data["campaign_id"] == campaign["id"]

    def test_create_lead_other_campaign_returns_404(self, client, second_user):
        other_campaign = insert_campaign(user_id=second_user["id"])
        resp = client.post(f"/campaigns/{other_campaign['id']}/leads", json={
            "email": "lead@test.com",
            "first_name": "Bob",
            "last_name": "Jones",
        })
        assert resp.status_code == 404

    def test_create_duplicate_email_returns_409(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        lead_data = {"email": "dup@test.com", "first_name": "A", "last_name": "B"}
        client.post(f"/campaigns/{campaign['id']}/leads", json=lead_data)
        resp = client.post(f"/campaigns/{campaign['id']}/leads", json=lead_data)
        assert resp.status_code == 409

    def test_create_lead_in_completed_campaign_returns_400(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="completed")
        resp = client.post(f"/campaigns/{campaign['id']}/leads", json={
            "email": "lead@test.com",
            "first_name": "A",
            "last_name": "B",
        })
        assert resp.status_code == 400


class TestBulkCreate:
    def test_bulk_create_leads(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        leads = [
            {"email": f"lead{i}@test.com", "first_name": f"First{i}", "last_name": f"Last{i}"}
            for i in range(5)
        ]
        resp = client.post(f"/campaigns/{campaign['id']}/leads/bulk", json={"leads": leads})
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    def test_bulk_deduplicates_against_existing(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        insert_lead(campaign_id=campaign["id"], email="existing@test.com")

        resp = client.post(f"/campaigns/{campaign['id']}/leads/bulk", json={
            "leads": [
                {"email": "existing@test.com", "first_name": "A", "last_name": "B"},
                {"email": "new@test.com", "first_name": "C", "last_name": "D"},
            ]
        })
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["email"] == "new@test.com"

    def test_bulk_deduplicates_within_batch(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        resp = client.post(f"/campaigns/{campaign['id']}/leads/bulk", json={
            "leads": [
                {"email": "same@test.com", "first_name": "A", "last_name": "B"},
                {"email": "same@test.com", "first_name": "C", "last_name": "D"},
            ]
        })
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_bulk_empty_list_returns_400(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        resp = client.post(f"/campaigns/{campaign['id']}/leads/bulk", json={"leads": []})
        assert resp.status_code == 400


class TestLeadDetail:
    def test_get_lead_detail_includes_campaign_name(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], name="Named Campaign")
        lead = insert_lead(campaign_id=campaign["id"])
        resp = client.get(f"/leads/{lead['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_name"] == "Named Campaign"

    def test_get_lead_detail_other_user_returns_404(self, client, second_user):
        other_campaign = insert_campaign(user_id=second_user["id"])
        other_lead = insert_lead(campaign_id=other_campaign["id"])
        resp = client.get(f"/leads/{other_lead['id']}")
        assert resp.status_code == 404

    def test_lead_activity(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        insert_email(lead_id=lead["id"], sequence_number=1, subject="First")
        insert_email(lead_id=lead["id"], sequence_number=2, subject="Second")
        insert_email(lead_id=lead["id"], sequence_number=3, subject="Third")

        resp = client.get(f"/leads/{lead['id']}/activity?campaign_id={campaign['id']}")
        assert resp.status_code == 200
        activity = resp.json()
        assert len(activity) == 3


class TestLeadUpdate:
    def test_update_lead_notes(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        resp = client.patch(f"/leads/{lead['id']}", json={"notes": "Updated notes here"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Updated notes here"

        # Verify in DB
        with get_cursor() as cur:
            cur.execute("SELECT notes FROM leads WHERE id = %s", (lead["id"],))
            assert cur.fetchone()["notes"] == "Updated notes here"

    def test_update_lead_other_user_returns_404(self, client, second_user):
        other_campaign = insert_campaign(user_id=second_user["id"])
        other_lead = insert_lead(campaign_id=other_campaign["id"], notes="original")
        resp = client.patch(f"/leads/{other_lead['id']}", json={"notes": "hacked"})
        assert resp.status_code == 404

        # Verify notes unchanged
        with get_cursor() as cur:
            cur.execute("SELECT notes FROM leads WHERE id = %s", (other_lead["id"],))
            assert cur.fetchone()["notes"] == "original"

    def test_delete_lead(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        lead = insert_lead(campaign_id=campaign["id"])
        resp = client.delete(f"/campaigns/{campaign['id']}/leads/{lead['id']}")
        assert resp.status_code == 200

        resp = client.get(f"/leads/{lead['id']}")
        assert resp.status_code == 404
