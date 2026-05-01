"""
Tests for the account-wide documents library and campaign attachment flow.

Upstream services (LlamaParse parser, LLM summariser) are mocked so tests
don't hit the network. The goal is to exercise the API contract:
validation, ownership, attach cap, join semantics.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest

from src.db.engine import get_cursor
from conftest import insert_campaign


def _fake_pdf_bytes(n: int = 2048) -> bytes:
    return b"%PDF-1.4\n" + (b"x" * n)


@pytest.fixture
def mock_upstreams():
    """Mock LlamaParse parse + LLM summarise to return a canned brief."""
    with (
        patch(
            "src.api.documents.parse_document",
            new=AsyncMock(return_value="# Parsed markdown\n\nFacts go here."),
        ) as p,
        patch(
            "src.api.documents.summarize_to_brief",
            new=AsyncMock(return_value="## Company\n\n- Founded 2003.\n- 400+ furnaces delivered.\n" * 6),
        ) as s,
    ):
        yield p, s


def _upload(client, filename: str = "deck.pdf") -> dict:
    """Helper: POST /documents and return the created document dict."""
    resp = client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(_fake_pdf_bytes()), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Library CRUD ────────────────────────────────────────────────────────


class TestUploadDocument:
    def test_upload_pdf_creates_library_entry(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        assert doc["name"] == "deck.pdf"
        assert doc["extension"] == ".pdf"
        assert doc["word_count"] > 0
        assert "400+ furnaces" in doc["brief"]

        with get_cursor() as cur:
            cur.execute(
                "SELECT name, brief FROM documents WHERE user_id = %s",
                (test_user["id"],),
            )
            row = cur.fetchone()
            assert row["name"] == "deck.pdf"
            assert "400+ furnaces" in row["brief"]

    def test_upload_rejects_unsupported_extension(self, client, test_user):
        resp = client.post(
            "/documents",
            files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_upload_rejects_empty_file(self, client, test_user):
        resp = client.post(
            "/documents",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_upload_rejects_oversized_file(self, client, test_user):
        huge = b"x" * (11 * 1024 * 1024)
        resp = client.post(
            "/documents",
            files={"file": ("big.pdf", io.BytesIO(huge), "application/pdf")},
        )
        assert resp.status_code == 413

    def test_upload_parser_failure_returns_422(self, client, test_user):
        from src.documents import DocumentParseError

        with patch(
            "src.api.documents.parse_document",
            new=AsyncMock(side_effect=DocumentParseError("no text extracted")),
        ):
            resp = client.post(
                "/documents",
                files={"file": ("scanned.pdf", io.BytesIO(_fake_pdf_bytes()), "application/pdf")},
            )
        assert resp.status_code == 422
        # Make sure nothing landed in the library on failure
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM documents WHERE user_id = %s",
                (test_user["id"],),
            )
            assert cur.fetchone()["c"] == 0


class TestListAndGetDocuments:
    def test_list_returns_only_callers_documents(self, client, client_user2, mock_upstreams):
        my_doc = _upload(client, "mine.pdf")
        _upload(client_user2, "theirs.pdf")

        resp = client.get("/documents")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert my_doc["id"] in ids
        assert len(resp.json()) == 1

    def test_get_document_returns_brief(self, client, mock_upstreams):
        doc = _upload(client)
        resp = client.get(f"/documents/{doc['id']}")
        assert resp.status_code == 200
        assert resp.json()["brief"] == doc["brief"]

    def test_get_document_cross_tenant_returns_404(self, client, client_user2, mock_upstreams):
        other = _upload(client_user2)
        resp = client.get(f"/documents/{other['id']}")
        assert resp.status_code == 404


class TestDeleteDocument:
    def test_delete_removes_from_library(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        resp = client.delete(f"/documents/{doc['id']}")
        assert resp.status_code == 200

        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM documents WHERE id = %s",
                (doc["id"],),
            )
            assert cur.fetchone()["c"] == 0

    def test_delete_cascades_campaign_attachments(self, client, test_user, mock_upstreams):
        """Deleting a doc should detach it from all campaigns it was on."""
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": [doc["id"]]},
        )

        client.delete(f"/documents/{doc['id']}")

        # Campaign still exists; attachment is gone
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as c FROM campaigns WHERE id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 1
            cur.execute(
                "SELECT COUNT(*) as c FROM campaign_documents WHERE campaign_id = %s",
                (campaign["id"],),
            )
            assert cur.fetchone()["c"] == 0

    def test_delete_cross_tenant_returns_404(self, client, client_user2, mock_upstreams):
        other = _upload(client_user2)
        resp = client.delete(f"/documents/{other['id']}")
        assert resp.status_code == 404


# ── Campaign attachment ─────────────────────────────────────────────────


class TestAttachToCampaign:
    def test_attach_single_document(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")

        resp = client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": [doc["id"]]},
        )
        assert resp.status_code == 200, resp.text
        attached = resp.json()
        assert len(attached) == 1
        assert attached[0]["id"] == doc["id"]

    def test_attach_two_documents_ok(self, client, test_user, mock_upstreams):
        d1 = _upload(client, "a.pdf")
        d2 = _upload(client, "b.pdf")
        campaign = insert_campaign(user_id=test_user["id"], status="draft")

        resp = client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": [d1["id"], d2["id"]]},
        )
        assert resp.status_code == 200
        assert {d["id"] for d in resp.json()} == {d1["id"], d2["id"]}

    def test_attach_three_documents_rejected(self, client, test_user, mock_upstreams):
        ids = [_upload(client, f"{i}.pdf")["id"] for i in range(3)]
        campaign = insert_campaign(user_id=test_user["id"], status="draft")

        resp = client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": ids},
        )
        assert resp.status_code == 400
        assert "at most 2" in resp.json()["detail"].lower()

    def test_attach_replaces_previous_set(self, client, test_user, mock_upstreams):
        d1 = _upload(client, "a.pdf")
        d2 = _upload(client, "b.pdf")
        campaign = insert_campaign(user_id=test_user["id"], status="draft")

        client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": [d1["id"]]})
        resp = client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": [d2["id"]]})
        assert resp.status_code == 200
        assert [d["id"] for d in resp.json()] == [d2["id"]]

    def test_attach_empty_list_clears_attachments(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": [doc["id"]]})

        resp = client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": []})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_attach_active_campaign_returns_400(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="active")
        resp = client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": [doc["id"]]},
        )
        assert resp.status_code == 400

    def test_attach_other_users_campaign_returns_404(self, client, second_user, mock_upstreams):
        doc = _upload(client)
        other_campaign = insert_campaign(user_id=second_user["id"], status="draft")
        resp = client.put(
            f"/campaigns/{other_campaign['id']}/documents",
            json={"document_ids": [doc["id"]]},
        )
        assert resp.status_code == 404

    def test_attach_other_users_document_returns_404(self, client, client_user2, test_user, mock_upstreams):
        """User 1 can't attach user 2's document to their own campaign."""
        their_doc = _upload(client_user2)
        my_campaign = insert_campaign(user_id=test_user["id"], status="draft")
        resp = client.put(
            f"/campaigns/{my_campaign['id']}/documents",
            json={"document_ids": [their_doc["id"]]},
        )
        assert resp.status_code == 404

    def test_attach_deduplicates_client_supplied_ids(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")

        resp = client.put(
            f"/campaigns/{campaign['id']}/documents",
            json={"document_ids": [doc["id"], doc["id"]]},
        )
        # Dedup -> 1 attachment, not a "3 > 2" rejection
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── Campaign response surfaces attached documents ──────────────────────


class TestCampaignResponseIncludesDocuments:
    def test_get_campaign_includes_documents_array(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": [doc["id"]]})

        resp = client.get(f"/campaigns/{campaign['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) == 1
        assert data["documents"][0]["id"] == doc["id"]
        assert data["documents"][0]["name"] == "deck.pdf"

    def test_get_campaign_with_no_docs_returns_empty_array(self, client, test_user):
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        resp = client.get(f"/campaigns/{campaign['id']}")
        assert resp.status_code == 200
        assert resp.json()["documents"] == []

    def test_list_campaigns_includes_documents(self, client, test_user, mock_upstreams):
        doc = _upload(client)
        campaign = insert_campaign(user_id=test_user["id"], status="draft")
        client.put(f"/campaigns/{campaign['id']}/documents", json={"document_ids": [doc["id"]]})

        resp = client.get("/campaigns")
        assert resp.status_code == 200
        campaigns = resp.json()
        target = next(c for c in campaigns if c["id"] == campaign["id"])
        assert len(target["documents"]) == 1
