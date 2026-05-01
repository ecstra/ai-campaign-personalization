import os
from typing import Any

import jwt
from fastapi import Header, HTTPException
from dotenv import load_dotenv

from ..db.engine import get_cursor

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"


async def get_current_user(authorization: str = Header(...)) -> dict[str, Any]:
    """
    FastAPI dependency that extracts and validates the Bearer JWT from the
    Authorization header. Returns a dict with user info from the database.

    Raises:
        HTTPException 401 on missing/invalid/expired token or unknown user.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization[len("Bearer "):]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, email, name, picture_url FROM users WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "picture_url": user["picture_url"],
    }
