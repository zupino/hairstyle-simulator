"""
JWT creation/verification and password hashing utilities.
FastAPI dependency helpers for role-based access control.
"""

from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt
import hashlib
import jwt

from backend import config, database

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    digest = hashlib.sha256(plain.encode()).hexdigest().encode()
    return "sha256:" + bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("sha256:"):
        digest = hashlib.sha256(plain.encode()).hexdigest().encode()
        return bcrypt.checkpw(digest, hashed[7:].encode())
    # Existing passlib bcrypt hashes used the first 72 UTF-8 bytes.
    return bcrypt.checkpw(plain.encode()[:72], hashed.encode())


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=config.ACCESS_TOKEN_TTL),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------

def _get_current_user(token: Annotated[str, Depends(_oauth2_scheme)]):
    payload = _decode_token(token)
    user_id = int(payload["sub"])
    user = database.get_user_by_id(user_id)
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")
    return user


def require_active_user(user=Depends(_get_current_user)):
    return user


def require_admin(user=Depends(_get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_operator_or_admin(user=Depends(_get_current_user)):
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return user
