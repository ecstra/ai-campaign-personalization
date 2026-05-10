import os
import httpx

from datetime import datetime, timedelta, timezone

from .encryption import EncryptionUtility
from src.db import DatabaseEngine

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

TOKEN_REFRESH_TIMEOUT = int(os.getenv("TOKEN_REFRESH_TIMEOUT_SECONDS", "15"))
TOKEN_EXPIRY_BUFFER_MINUTES = int(os.getenv("TOKEN_EXPIRY_BUFFER_MINUTES", "5"))
TOKEN_DEFAULT_EXPIRY_SECONDS = int(os.getenv("TOKEN_DEFAULT_EXPIRY_SECONDS", "3600"))

class TokenUtility:

    @staticmethod
    def store_user_tokens(
        user_id: str,
        access_token: str,
        refresh_token: str | None,
        expiry: datetime,
    ) -> None:
        encrypted_access = EncryptionUtility.encrypt_token(access_token)

        with DatabaseEngine.get_cursor(commit=True) as cur:
            if refresh_token:
                encrypted_refresh = EncryptionUtility.encrypt_token(refresh_token)
                cur.execute(
                    """
                    UPDATE users
                    SET access_token_encrypted = %s,
                        refresh_token_encrypted = %s,
                        token_expiry = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (encrypted_access, encrypted_refresh, expiry, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE users
                    SET access_token_encrypted = %s,
                        token_expiry = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (encrypted_access, expiry, user_id),
                )

    @staticmethod
    def get_user_tokens(user_id: str) -> dict | None:
        with DatabaseEngine.get_cursor() as cur:
            cur.execute(
                """
                SELECT access_token_encrypted, refresh_token_encrypted, token_expiry
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

        if not row or not row["access_token_encrypted"]:
            return None

        return {
            "access_token": EncryptionUtility.decrypt_token(row["access_token_encrypted"]),
            "refresh_token": (
                EncryptionUtility.decrypt_token(row["refresh_token_encrypted"])
                if row["refresh_token_encrypted"]
                else None
            ),
            "token_expiry": row["token_expiry"],
        }

    @staticmethod
    def refresh_access_token(user_id: str) -> str:
        tokens = TokenUtility.get_user_tokens(user_id)
        if not tokens or not tokens["refresh_token"]:
            raise ValueError(f"No refresh token stored for user {user_id}")

        try:
            response = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "refresh_token": tokens["refresh_token"],
                    "grant_type": "refresh_token",
                },
                timeout=TOKEN_REFRESH_TIMEOUT,
            )
        except httpx.HTTPError as e:
            raise ValueError(f"Google token refresh request failed: {e}") from e

        if response.status_code != 200:
            raise ValueError(
                f"Google token refresh failed (status {response.status_code}). "
                "The user may need to re-authenticate."
            )

        try:
            data = response.json()
        except ValueError as e:
            raise ValueError("Google token refresh returned invalid JSON response") from e

        new_access_token = data.get("access_token")
        if not new_access_token:
            raise ValueError("Google token refresh response missing access_token")

        expires_in = data.get("expires_in", TOKEN_DEFAULT_EXPIRY_SECONDS)
        new_expiry = datetime.now(timezone.utc).replace(
            microsecond=0
        ) + timedelta(seconds=expires_in)

        TokenUtility.store_user_tokens(
            user_id=user_id,
            access_token=new_access_token,
            refresh_token=None,
            expiry=new_expiry,
        )

        return new_access_token

    @staticmethod
    def get_valid_access_token(user_id: str) -> str:
        tokens = TokenUtility.get_user_tokens(user_id)
        if not tokens:
            raise ValueError(f"No tokens stored for user {user_id}")

        now = datetime.now(timezone.utc)
        buffer = timedelta(minutes=TOKEN_EXPIRY_BUFFER_MINUTES)

        if tokens["token_expiry"] and tokens["token_expiry"] <= now + buffer:
            return TokenUtility.refresh_access_token(user_id)

        return tokens["access_token"]