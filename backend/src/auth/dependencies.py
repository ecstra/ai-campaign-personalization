import os
import jwt

from fastapi import Header, HTTPException

from ..db import DatabaseEngine

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    raise ValueError(
        "JWT_SECRET environment variable is not set. "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )
JWT_ALGORITHM = "HS256"


async def get_current_user(authorization: str = Header(...)) -> dict[str, object]:
    if not authorization or " " not in authorization:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    with DatabaseEngine.get_cursor() as cur:
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
