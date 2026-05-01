import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
from dotenv import load_dotenv

from .encryption import encrypt_token
from .dependencies import get_current_user, JWT_SECRET, JWT_ALGORITHM
from ..db.engine import get_cursor
from ..logger import logger

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scopes: identity + full Gmail access for XOAUTH2 IMAP/SMTP
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://mail.google.com/",
]

JWT_EXPIRY_DAYS = 7

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthCallbackRequest(BaseModel):
    code: str
    state: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture_url: str | None


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


@router.get("/google/login")
async def google_login():
    """Return the Google OAuth2 authorization URL for the frontend to redirect to."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI.",
        )

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{httpx.QueryParams(params)}"

    return {"url": auth_url, "state": state}


@router.post("/google/callback", response_model=AuthResponse)
async def google_callback(body: AuthCallbackRequest):
    """
    Exchange the Google authorization code for tokens, create/update the user,
    and return a JWT session token.
    """
    # Exchange code for tokens
    token_response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": body.code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )

    if token_response.status_code != 200:
        logger.error(f"Google token exchange failed: {token_response.text}")
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    token_data = token_response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    raw_id_token = token_data.get("id_token")
    expires_in = token_data.get("expires_in", 3600)

    if not raw_id_token:
        raise HTTPException(status_code=400, detail="No id_token in Google response")

    # Verify and decode the ID token
    try:
        id_info = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        logger.error(f"Google ID token verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google ID token")

    google_id = id_info["sub"]
    email = id_info["email"]
    name = id_info.get("name", email.split("@")[0])
    picture_url = id_info.get("picture")
    granted_scopes = token_data.get("scope", " ".join(SCOPES))

    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Encrypt tokens for storage
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    # Upsert user
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO users (google_id, email, name, picture_url,
                               access_token_encrypted, refresh_token_encrypted,
                               token_expiry, scopes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (google_id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture_url = EXCLUDED.picture_url,
                access_token_encrypted = EXCLUDED.access_token_encrypted,
                refresh_token_encrypted = COALESCE(EXCLUDED.refresh_token_encrypted, users.refresh_token_encrypted),
                token_expiry = EXCLUDED.token_expiry,
                scopes = EXCLUDED.scopes,
                updated_at = NOW()
            RETURNING id
            """,
            (
                google_id,
                email,
                name,
                picture_url,
                encrypted_access,
                encrypted_refresh,
                token_expiry,
                granted_scopes,
            ),
        )
        user_row = cur.fetchone()
        user_id = str(user_row["id"])

    logger.info(f"User authenticated: {email} (id={user_id})")

    # Create JWT session token
    jwt_payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    session_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return AuthResponse(
        token=session_token,
        user=UserResponse(
            id=user_id,
            email=email,
            name=name,
            picture_url=picture_url,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        picture_url=user["picture_url"],
    )
