"""Tests for IMAP reply detection: DB helpers and header decoding."""

from datetime import datetime, timedelta, timezone

import pytest

from src.mail.imap import _get_lead_emails_for_user, _get_earliest_campaign_start, _decode_header_value
from conftest import insert_user, insert_campaign, insert_lead, insert_email


class TestGetLeadEmailsForUser:
    def test_returns_active_campaign_leads(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        lead1 = insert_lead(campaign_id=campaign["id"], email="alice@example.com")
        lead2 = insert_lead(campaign_id=campaign["id"], email="bob@example.com")
        insert_email(lead_id=lead1["id"], sequence_number=1, message_id="<msg-1@test>")
        insert_email(lead_id=lead2["id"], sequence_number=1, message_id="<msg-2@test>")

        lead_map = _get_lead_emails_for_user(user["id"])
        assert "alice@example.com" in lead_map
        assert "bob@example.com" in lead_map
        assert lead_map["alice@example.com"][0]["message_id"] == "<msg-1@test>"

    def test_excludes_replied_leads(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="active")
        insert_lead(
            campaign_id=campaign["id"],
            email="replied@example.com",
            has_replied=True,
            status="replied",
        )

        lead_map = _get_lead_emails_for_user(user["id"])
        assert "replied@example.com" not in lead_map

    def test_excludes_paused_campaign(self):
        user = insert_user()
        campaign = insert_campaign(user_id=user["id"], status="paused")
        insert_lead(campaign_id=campaign["id"], email="lead@example.com")

        lead_map = _get_lead_emails_for_user(user["id"])
        assert len(lead_map) == 0


class TestGetEarliestCampaignStart:
    def test_returns_earliest(self):
        user = insert_user()
        # Two campaigns with different timestamps
        c1 = insert_campaign(user_id=user["id"], name="First", status="active")
        c2 = insert_campaign(user_id=user["id"], name="Second", status="active")

        result = _get_earliest_campaign_start(user["id"])
        assert result is not None
        assert isinstance(result, datetime)

    def test_returns_none_when_no_active(self):
        user = insert_user()
        insert_campaign(user_id=user["id"], status="paused")

        result = _get_earliest_campaign_start(user["id"])
        assert result is None


class TestDecodeHeaderValue:
    def test_plain_ascii(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_mime_encoded_utf8(self):
        # =?UTF-8?B?SGVsbG8=?= is "Hello" in base64 UTF-8
        result = _decode_header_value("=?UTF-8?B?SGVsbG8=?=")
        assert result == "Hello"

    def test_none_returns_empty(self):
        assert _decode_header_value(None) == ""
