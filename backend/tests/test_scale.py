"""
Scale tests: verify the system stays correct and reasonably fast under
realistic CSV-import-sized loads (500 leads per campaign).

These tests run against the same test Postgres DB as the rest of the suite.
They focus on:
  - Correctness at scale (no dropped/duplicated rows)
  - Single-round-trip bulk inserts (not O(n) per-row)
  - List / analytics / bulk-delete endpoints staying responsive
  - Scheduler's eligible-lead query respecting LIMIT under heavy load
"""

import time

import pytest

from src.db.engine import get_cursor
from src.scheduler.job import _get_eligible_leads, CAMPAIGN_EMAIL_RATE_LIMIT
from conftest import insert_campaign, insert_lead, insert_email


# Generous ceilings — we're not benchmarking, just catching O(n²) regressions
# or accidental per-row network calls.
BULK_INSERT_500_MAX_SECONDS = 10.0
LIST_500_MAX_SECONDS = 2.0
BULK_DELETE_500_MAX_SECONDS = 3.0
STATS_MAX_SECONDS = 3.0


def _make_leads(count: int, prefix: str = "lead") -> list[dict]:
    return [
        {
            "email": f"{prefix}{i}@example.com",
            "first_name": f"First{i}",
            "last_name": f"Last{i}",
            "company": f"Company {i}",
            "title": "VP Sales",
        }
        for i in range(count)
    ]


class TestBulkImportScale:
    def test_bulk_import_500_leads_succeeds(self, client, test_user):
        """All 500 rows land in the DB, response reflects the full set."""
        campaign = insert_campaign(user_id=test_user["id"])
        leads = _make_leads(500)

        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": leads},
        )

        assert resp.status_code == 200
        assert len(resp.json()) == 500

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM leads WHERE campaign_id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 500

    def test_bulk_import_500_leads_within_time_budget(self, client, test_user):
        """
        Regression guard: bulk import must use a single multi-row INSERT,
        not N round-trips. On a fresh local Postgres, 500 rows finish in
        well under a second; we allow 10s as a safety margin for slow CI.
        A per-row implementation against a remote DB would easily blow this.
        """
        campaign = insert_campaign(user_id=test_user["id"])
        leads = _make_leads(500)

        start = time.perf_counter()
        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": leads},
        )
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < BULK_INSERT_500_MAX_SECONDS, (
            f"Bulk import of 500 leads took {elapsed:.2f}s, "
            f"expected < {BULK_INSERT_500_MAX_SECONDS}s. "
            f"This likely means we regressed to per-row INSERTs."
        )

    def test_bulk_import_with_500_intra_batch_duplicates(self, client, test_user):
        """500 rows where every email is repeated once in the batch → 250 unique."""
        campaign = insert_campaign(user_id=test_user["id"])
        # 250 unique emails, each appearing twice
        leads = []
        for i in range(250):
            leads.append({
                "email": f"dup{i}@test.com",
                "first_name": "A",
                "last_name": "B",
            })
            leads.append({
                "email": f"dup{i}@test.com",
                "first_name": "A-second",
                "last_name": "B-second",
            })

        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": leads},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 250

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT email) as c FROM leads WHERE campaign_id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 250

    def test_bulk_import_with_existing_leads_skips_them(self, client, test_user):
        """
        Campaign already has 100 leads. Upload a CSV of 500 where 100 overlap.
        Expect 400 new, 100 skipped, total 500 in DB.
        """
        campaign = insert_campaign(user_id=test_user["id"])

        # Pre-seed 100 existing leads
        for i in range(100):
            insert_lead(
                campaign_id=campaign["id"],
                email=f"existing{i}@test.com",
            )

        # Upload batch: 100 overlap with existing + 400 new
        leads = [
            {"email": f"existing{i}@test.com", "first_name": "X", "last_name": "Y"}
            for i in range(100)
        ] + [
            {"email": f"new{i}@test.com", "first_name": "X", "last_name": "Y"}
            for i in range(400)
        ]

        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": leads},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 400

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM leads WHERE campaign_id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 500

    def test_bulk_import_all_duplicates_returns_empty_list(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        insert_lead(campaign_id=campaign["id"], email="only@test.com")

        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={
                "leads": [
                    {"email": "only@test.com", "first_name": "A", "last_name": "B"},
                    {"email": "only@test.com", "first_name": "C", "last_name": "D"},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestListLeadsScale:
    def test_list_500_leads_within_time_budget(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": _make_leads(500)},
        )

        start = time.perf_counter()
        resp = client.get(f"/campaigns/{campaign['id']}/leads")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert len(resp.json()) == 500
        assert elapsed < LIST_500_MAX_SECONDS, (
            f"Listing 500 leads took {elapsed:.2f}s, expected < {LIST_500_MAX_SECONDS}s"
        )


class TestBulkDeleteScale:
    def test_bulk_delete_500_leads(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"])
        bulk_resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk",
            json={"leads": _make_leads(500)},
        )
        assert bulk_resp.status_code == 200, bulk_resp.text
        lead_ids = [lead["id"] for lead in bulk_resp.json()]
        assert len(lead_ids) == 500

        start = time.perf_counter()
        resp = client.post(
            f"/campaigns/{campaign['id']}/leads/bulk-delete",
            json={"lead_ids": lead_ids},
        )
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert resp.json()["count"] == 500
        assert elapsed < BULK_DELETE_500_MAX_SECONDS

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM leads WHERE campaign_id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 0

    def test_bulk_delete_partial_ownership(self, client, test_user, second_user):
        """
        User A tries to bulk-delete leads from a campaign owned by user B.
        Deletion must reject (404) because campaign ownership check fails.
        No leads should be deleted.
        """
        other_campaign = insert_campaign(user_id=second_user["id"])
        other_lead = insert_lead(campaign_id=other_campaign["id"])

        resp = client.post(
            f"/campaigns/{other_campaign['id']}/leads/bulk-delete",
            json={"lead_ids": [other_lead["id"]]},
        )
        assert resp.status_code == 404

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM leads WHERE id = %s",
                (other_lead["id"],),
            )
            assert cur.fetchone()["c"] == 1  # still there


class TestStatsAtScale:
    def test_campaign_stats_with_500_leads_and_mixed_history(self, client, test_user):
        """Stats endpoint must stay fast and correct with 500 leads, each with some emails."""
        campaign = insert_campaign(user_id=test_user["id"])

        # 500 leads: 100 replied, 50 failed, 350 pending
        for i in range(500):
            if i < 100:
                status = "replied"
                has_replied = True
                current_seq = 2
            elif i < 150:
                status = "failed"
                has_replied = False
                current_seq = 1
            else:
                status = "pending"
                has_replied = False
                current_seq = 0

            lead = insert_lead(
                campaign_id=campaign["id"],
                email=f"stat{i}@test.com",
                status=status,
                has_replied=has_replied,
                current_sequence=current_seq,
            )
            # Give each non-pending lead an email record
            if current_seq > 0:
                insert_email(lead_id=lead["id"], sequence_number=1, status="sent")

        start = time.perf_counter()
        resp = client.get(f"/campaigns/{campaign['id']}/stats")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_leads"] == 500
        assert data["reply_count"] == 100
        assert data["reply_rate"] == 20.0
        assert data["leads_by_status"]["replied"] == 100
        assert data["leads_by_status"]["failed"] == 50
        assert data["leads_by_status"]["pending"] == 350
        assert elapsed < STATS_MAX_SECONDS


class TestSchedulerAtScale:
    def test_eligible_leads_respects_rate_limit_with_500_pending(self, test_user):
        """
        500 pending leads on a single active campaign. The eligible-leads
        query must return at most CAMPAIGN_EMAIL_RATE_LIMIT rows, not all 500.
        """
        campaign = insert_campaign(user_id=test_user["id"], status="active")
        for i in range(500):
            insert_lead(
                campaign_id=campaign["id"],
                email=f"sched{i}@test.com",
                status="pending",
                next_email_at="NOW()",
            )

        eligible = _get_eligible_leads()
        # Same user+campaign, so rate limit caps the batch
        assert len(eligible) <= CAMPAIGN_EMAIL_RATE_LIMIT
        assert all(lead["campaign_id"] == campaign["id"] for lead in eligible)

    def test_eligible_leads_ignores_paused_campaign_leads(self, test_user):
        active = insert_campaign(user_id=test_user["id"], name="Active", status="active")
        paused = insert_campaign(user_id=test_user["id"], name="Paused", status="paused")

        for i in range(20):
            insert_lead(
                campaign_id=active["id"],
                email=f"active{i}@test.com",
                status="pending",
                next_email_at="NOW()",
            )
            insert_lead(
                campaign_id=paused["id"],
                email=f"paused{i}@test.com",
                status="pending",
                next_email_at="NOW()",
            )

        eligible = _get_eligible_leads()
        active_ids = {lead["campaign_id"] for lead in eligible}
        assert active["id"] in active_ids
        assert paused["id"] not in active_ids
