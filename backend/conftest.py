"""
Shared test fixtures for the backend test suite.

IMPORTANT: Environment variables are set before any src.* imports because
engine.py, encryption.py, agent.py, and oauth.py all read env vars at module
load time. The test_db fixture (session-scoped, autouse) handles this.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Generator

import pytest
from cryptography.fernet import Fernet

# ── Set env vars BEFORE importing anything from src ──────────────────────────
# These must be set at module level so they're available when src modules load.

_TEST_DB_URI = os.environ.get("TEST_DATABASE_URI")
if not _TEST_DB_URI:
    pytest.skip(
        "TEST_DATABASE_URI not set. Provide a Postgres connection string for the test database.",
        allow_module_level=True,
    )

os.environ["DATABASE_URI"] = _TEST_DB_URI
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-jwt-secret-not-for-production"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:5173/auth/callback"
os.environ["GMAIL_DAILY_SEND_LIMIT"] = "450"
os.environ["GMAIL_INTER_SEND_DELAY_MS"] = "0"  # No delay in tests

# moonlight-ai validates the provider source at import time, so we must use
# a real provider name. The fake API key ensures no actual LLM calls are made.
os.environ.setdefault("LLM_SOURCE", "groq")
os.environ.setdefault("LLM_API_KEY", "gsk_fake_test_key_not_real")
os.environ.setdefault("LLM_MODEL", "llama-3.3-70b-versatile")

# ── Now safe to import src modules ──────────────────────────────────────────

from src.db.engine import init_pool, close_pool, get_cursor  # noqa: E402
from src.db.base import init_db  # noqa: E402
from src.auth.encryption import encrypt_token  # noqa: E402
from src.auth.dependencies import get_current_user  # noqa: E402

# Import app last (it triggers router registration)
from app import app  # noqa: E402


# ── Helper Functions ────────────────────────────────────────────────────────


def insert_user(
    google_id: str = "google_test_1",
    email: str = "test@gmail.com",
    name: str = "Test User",
    picture_url: str | None = None,
    store_tokens: bool = True,
) -> dict[str, Any]:
    """Insert a user directly into the DB. Returns user dict with 'id'."""
    encrypted_access = encrypt_token("fake-access-token") if store_tokens else None
    encrypted_refresh = encrypt_token("fake-refresh-token") if store_tokens else None
    token_expiry = datetime.now(timezone.utc) + timedelta(hours=1) if store_tokens else None

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO users (google_id, email, name, picture_url,
                               access_token_encrypted, refresh_token_encrypted,
                               token_expiry, scopes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, name, picture_url
            """,
            (google_id, email, name, picture_url,
             encrypted_access, encrypted_refresh, token_expiry,
             "openid email profile https://mail.google.com/"),
        )
        row = cur.fetchone()
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "name": row["name"],
        "picture_url": row["picture_url"],
    }


def insert_campaign(
    user_id: str,
    name: str = "Test Campaign",
    sender_name: str = "Test Sender",
    sender_email: str = "test@gmail.com",
    goal: str = "Get meetings booked",
    status: str = "active",
    max_follow_ups: int = 3,
    follow_up_delay_minutes: int = 2880,
) -> dict[str, Any]:
    """Insert a campaign directly into the DB."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO campaigns (user_id, name, sender_name, sender_email, goal,
                                   status, max_follow_ups, follow_up_delay_minutes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, name, sender_name, sender_email, goal,
                      status, max_follow_ups, follow_up_delay_minutes,
                      created_at, updated_at
            """,
            (user_id, name, sender_name, sender_email, goal,
             status, max_follow_ups, follow_up_delay_minutes),
        )
        row = cur.fetchone()
    return {k: str(v) if k == "id" or k == "user_id" else v for k, v in row.items()}


def insert_lead(
    campaign_id: str,
    email: str = "lead@example.com",
    first_name: str = "Jane",
    last_name: str = "Doe",
    company: str | None = "Acme Corp",
    title: str | None = "VP Marketing",
    notes: str | None = None,
    status: str = "pending",
    has_replied: bool = False,
    current_sequence: int = 0,
    next_email_at: str | None = "NOW()",
    locked_at: str | None = None,
) -> dict[str, Any]:
    """Insert a lead directly into the DB."""
    # Build next_email_at expression
    next_email_expr = next_email_at if next_email_at else "NULL"

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            INSERT INTO leads (campaign_id, email, first_name, last_name, company,
                               title, notes, status, has_replied, current_sequence,
                               next_email_at, locked_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {next_email_expr}, %s)
            RETURNING id, campaign_id, email, first_name, last_name, company,
                      title, notes, status, has_replied, current_sequence,
                      next_email_at, locked_at, created_at
            """,
            (campaign_id, email, first_name, last_name, company,
             title, notes, status, has_replied, current_sequence, locked_at),
        )
        row = cur.fetchone()
    return {k: str(v) if k in ("id", "campaign_id") else v for k, v in row.items()}


def insert_email(
    lead_id: str,
    sequence_number: int = 1,
    subject: str = "Test Subject",
    body: str = "<p>Test body</p>",
    status: str = "sent",
    message_id: str | None = None,
    in_reply_to: str | None = None,
    sent_at: str = "NOW()",
) -> dict[str, Any]:
    """Insert an email record directly into the DB."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            INSERT INTO emails (lead_id, sequence_number, subject, body, status,
                                message_id, in_reply_to, sent_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, {sent_at})
            RETURNING id, lead_id, sequence_number, subject, body, status,
                      message_id, in_reply_to, sent_at, created_at
            """,
            (lead_id, sequence_number, subject, body, status, message_id, in_reply_to),
        )
        row = cur.fetchone()
    return {k: str(v) if k in ("id", "lead_id") else v for k, v in row.items()}


# ── Session-scoped Fixtures ─────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def test_db() -> Generator[None, None, None]:
    """
    Initialize test database: create pool, tables, and migrations.
    Also overrides the app lifespan so TestClient doesn't call init_pool/close_pool
    (which would destroy the pool managed here).

    Installs a single, session-scoped auth override that resolves the caller
    from a per-request header (X-Test-User-Id). This lets multiple client
    fixtures coexist in the same test — each TestClient sets its own header
    and the override looks up that user. The previous design had each client
    fixture install its own override into the same dependency slot, which
    meant whichever ran later clobbered the earlier one — fine for single-
    client tests, broken for cross-tenant tests.
    """
    from contextlib import asynccontextmanager
    from fastapi import HTTPException, Request

    @asynccontextmanager
    async def _test_lifespan(app_instance):  # type: ignore
        yield  # No-op: pool is managed by this fixture, not the app

    app.router.lifespan_context = _test_lifespan

    async def _resolve_test_user(request: Request) -> dict[str, Any]:
        """
        Reads X-Test-User-Id from the request and loads that user's row
        directly from the test DB. Tests set this header via the
        TestClient's default headers (see the client fixture).
        """
        user_id = request.headers.get("X-Test-User-Id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Missing X-Test-User-Id (test config error)")
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, email, name, picture_url FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Test user not found")
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "name": row["name"],
            "picture_url": row["picture_url"],
        }

    app.dependency_overrides[get_current_user] = _resolve_test_user

    init_pool()
    init_db()
    yield
    # Teardown: drop all tables
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DROP TABLE IF EXISTS emails CASCADE;
            DROP TABLE IF EXISTS leads CASCADE;
            DROP TABLE IF EXISTS campaigns CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS schema_migrations CASCADE;
            """
        )
    app.dependency_overrides.pop(get_current_user, None)
    close_pool()


# ── Function-scoped Fixtures ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_tables(test_db: None) -> None:
    """Truncate all tables before each test for isolation. Depends on test_db to ensure pool is ready."""
    with get_cursor(commit=True) as cur:
        cur.execute("TRUNCATE users, campaigns, leads, emails CASCADE")


@pytest.fixture()
def test_user() -> dict[str, Any]:
    """Create a test user with stored OAuth tokens."""
    return insert_user(
        google_id="google_test_1",
        email="testuser@gmail.com",
        name="Test User",
    )


@pytest.fixture()
def second_user() -> dict[str, Any]:
    """Create a second user for multi-tenancy isolation tests."""
    return insert_user(
        google_id="google_test_2",
        email="seconduser@gmail.com",
        name="Second User",
    )


class _PrefixedTestClient:
    """
    Wrapper around FastAPI TestClient that auto-prepends /api to request paths.
    All API routes are mounted under /api (for Caddy reverse-proxy in prod),
    but tests are written against bare paths for readability.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _prefix(self, url: str) -> str:
        if url.startswith("http") or url.startswith("/api"):
            return url
        if url.startswith("/"):
            return "/api" + url
        return "/api/" + url

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._client.get(self._prefix(url), **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._client.post(self._prefix(url), **kwargs)

    def put(self, url: str, **kwargs: Any) -> Any:
        return self._client.put(self._prefix(url), **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Any:
        return self._client.patch(self._prefix(url), **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Any:
        return self._client.delete(self._prefix(url), **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        return self._client.request(method, self._prefix(url), **kwargs)


def _make_client(user_id: str) -> Any:
    """
    Build an authenticated TestClient that tags every request with the
    X-Test-User-Id header. The session-scoped auth override in test_db
    resolves that header to the real user row, so multiple clients can
    coexist in the same test (cross-tenant cases) without fighting over
    a single dependency-override slot.
    """
    from fastapi.testclient import TestClient

    c = TestClient(app)
    c.headers["X-Test-User-Id"] = user_id
    return c


@pytest.fixture()
def client(test_user: dict[str, Any]):
    """TestClient authenticated as test_user. Auto-prefixes /api to paths."""
    with _make_client(test_user["id"]) as c:
        yield _PrefixedTestClient(c)


@pytest.fixture()
def client_user2(second_user: dict[str, Any]):
    """TestClient authenticated as second_user. Auto-prefixes /api to paths."""
    with _make_client(second_user["id"]) as c:
        yield _PrefixedTestClient(c)


@pytest.fixture()
def test_campaign(test_user: dict[str, Any]) -> dict[str, Any]:
    """Create an active campaign owned by test_user."""
    return insert_campaign(user_id=test_user["id"], sender_email=test_user["email"])


@pytest.fixture()
def test_lead(test_campaign: dict[str, Any]) -> dict[str, Any]:
    """Create a pending lead in test_campaign with next_email_at=NOW()."""
    return insert_lead(
        campaign_id=test_campaign["id"],
        email="lead@example.com",
        first_name="Jane",
        last_name="Doe",
        company="Acme Corp",
        title="VP Marketing",
        notes="Series A, 50 employees",
    )
