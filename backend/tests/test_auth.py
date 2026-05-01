"""Tests for authentication: encryption, JWT, OAuth callback, token storage."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.auth.encryption import encrypt_token, decrypt_token
from src.auth.dependencies import get_current_user, JWT_SECRET, JWT_ALGORITHM
from src.auth.tokens import store_user_tokens, get_user_tokens
from src.db.engine import get_cursor
from app import app
from conftest import insert_user


# ── Encryption ──────────────────────────────────────────────────────────────


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "my_secret_access_token_12345"
        encrypted = encrypt_token(original)
        decrypted = decrypt_token(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_ciphertext(self):
        """Fernet uses random IV, so encrypting the same string twice produces different ciphertexts."""
        token = "same_token"
        enc1 = encrypt_token(token)
        enc2 = encrypt_token(token)
        assert enc1 != enc2
        # Both decrypt to the same value
        assert decrypt_token(enc1) == decrypt_token(enc2) == token

    def test_decrypt_invalid_ciphertext(self):
        with pytest.raises(InvalidToken):
            decrypt_token("this-is-not-valid-fernet-ciphertext")


# ── JWT and get_current_user ────────────────────────────────────────────────


class TestJWT:
    def _make_jwt(self, user_id: str, email: str = "test@gmail.com", **extra) -> str:
        payload = {
            "user_id": user_id,
            "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
            **extra,
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    @pytest.mark.asyncio
    async def test_valid_jwt_returns_user(self, test_user):
        token = self._make_jwt(test_user["id"], test_user["email"])
        header = f"Bearer {token}"
        user = await get_current_user(authorization=header)
        assert user["id"] == test_user["id"]
        assert user["email"] == test_user["email"]

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_401(self, test_user):
        payload = {
            "user_id": test_user["id"],
            "email": test_user["email"],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_jwt_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_bearer_prefix_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Token abc123")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_for_deleted_user_returns_401(self, test_user):
        token = self._make_jwt(test_user["id"], test_user["email"])
        # Delete the user
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (test_user["id"],))
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401


# ── Token Storage ───────────────────────────────────────────────────────────


class TestTokenStorage:
    def test_store_and_retrieve_tokens(self, test_user):
        expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        store_user_tokens(test_user["id"], "new-access", "new-refresh", expiry)

        tokens = get_user_tokens(test_user["id"])
        assert tokens is not None
        assert tokens["access_token"] == "new-access"
        assert tokens["refresh_token"] == "new-refresh"

    def test_store_without_refresh_keeps_existing(self, test_user):
        expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        store_user_tokens(test_user["id"], "access-1", "original-refresh", expiry)

        # Store again without refresh token
        new_expiry = datetime.now(timezone.utc) + timedelta(hours=3)
        store_user_tokens(test_user["id"], "access-2", None, new_expiry)

        tokens = get_user_tokens(test_user["id"])
        assert tokens is not None
        assert tokens["access_token"] == "access-2"
        assert tokens["refresh_token"] == "original-refresh"


# ── OAuth Endpoints ─────────────────────────────────────────────────────────


class TestOAuth:
    def test_google_login_returns_auth_url(self):
        with TestClient(app) as c:
            resp = c.get("/api/auth/google/login")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "accounts.google.com" in data["url"]
        assert "mail.google.com" in data["url"]
        assert "state" in data

    @patch("src.auth.oauth.google_id_token.verify_oauth2_token")
    @patch("src.auth.oauth.httpx.post")
    def test_google_callback_creates_user_and_returns_jwt(
        self, mock_post, mock_verify
    ):
        # Mock Google token exchange response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "google-access-token",
            "refresh_token": "google-refresh-token",
            "expires_in": 3600,
            "id_token": "fake-id-token",
            "scope": "openid email profile https://mail.google.com/",
        }
        mock_post.return_value = mock_response

        # Mock ID token verification
        mock_verify.return_value = {
            "sub": "google_user_123",
            "email": "newuser@gmail.com",
            "name": "New User",
            "picture": "https://photo.url/pic.jpg",
        }

        with TestClient(app) as c:
            resp = c.post("/api/auth/google/callback", json={"code": "auth-code", "state": "test-state"})

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "newuser@gmail.com"
        assert data["user"]["name"] == "New User"

        # Verify JWT decodes correctly
        decoded = jwt.decode(data["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert decoded["email"] == "newuser@gmail.com"

        # Verify user was created in DB
        with get_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE google_id = %s", ("google_user_123",))
            user = cur.fetchone()
        assert user is not None
        assert user["email"] == "newuser@gmail.com"

    @patch("src.auth.oauth.google_id_token.verify_oauth2_token")
    @patch("src.auth.oauth.httpx.post")
    def test_google_callback_upserts_existing_user(
        self, mock_post, mock_verify
    ):
        # Pre-create user
        existing = insert_user(google_id="google_returning", email="returning@gmail.com", name="Old Name")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "id_token": "fake-id-token",
            "scope": "openid email profile https://mail.google.com/",
        }
        mock_post.return_value = mock_response

        mock_verify.return_value = {
            "sub": "google_returning",
            "email": "returning@gmail.com",
            "name": "Updated Name",
            "picture": None,
        }

        with TestClient(app) as c:
            resp = c.post("/api/auth/google/callback", json={"code": "code", "state": "state"})

        assert resp.status_code == 200
        data = resp.json()
        # Same user ID, updated name
        assert data["user"]["id"] == existing["id"]
        assert data["user"]["name"] == "Updated Name"
