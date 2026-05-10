import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

from .encryption import EncryptionUtility
from ..db import DatabaseEngine

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

class TokenUtility:

    @staticmethod
    def store_user_tokens(
        user_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expiry: datetime,
    ) -> None:
        """Encrypt and persist OAuth tokens for a user."""
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
    def get_user_tokens(
        user_id: str,
    ) -> Optional[dict]:
        """
        Return decrypted tokens and expiry for a user.
        Returns None if user has no tokens stored.
        """
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
    def refresh_access_token(
        user_id: str,
    ) -> str:
        """
        Use the stored refresh token to get a new access token from Google.
        Updates the DB with the new access token and expiry.
        Raises ValueError if the user has no refresh token or Google rejects the request.
        """
        tokens = TokenUtility.get_user_tokens(user_id)
        if not tokens or not tokens["refresh_token"]:
            raise ValueError(f"No refresh token stored for user {user_id}")

        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=15,
        )

        if response.status_code != 200:
            raise ValueError(
                f"Google token refresh failed (status {response.status_code}). "
                "The user may need to re-authenticate."
            )

        data = response.json()
        new_access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
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
    def get_valid_access_token(
        user_id: str,
    ) -> str:
        """
        Return a valid (non-expired) access token for a user.
        Refreshes automatically if the current token is expired or about to expire.
        """
        tokens = TokenUtility.get_user_tokens(user_id)
        if not tokens:
            raise ValueError(f"No tokens stored for user {user_id}")

        now = datetime.now(timezone.utc)
        buffer = timedelta(minutes=5)

        if tokens["token_expiry"] and tokens["token_expiry"] <= now + buffer:
            return TokenUtility.refresh_access_token(user_id)

        return tokens["access_token"]
