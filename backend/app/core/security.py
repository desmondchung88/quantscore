"""Password hashing and JWT issue/verify."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import mysql

_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET,
                          algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Resolve the caller, or 401. Every protected route depends on this."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    claims = _decode(creds.credentials)
    user = mysql.query_one(
        "SELECT user_id, username, email, created_at FROM users WHERE user_id = :uid",
        {"uid": int(claims["sub"])},
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    if creds is None:
        return None
    try:
        return current_user(creds)
    except HTTPException:
        return None


def assert_owns_portfolio(user_id: int, portfolio_id: int) -> dict:
    """Authorisation check -- a user may only touch their own portfolio."""
    row = mysql.query_one(
        "SELECT portfolio_id, user_id, name, initial_cash, cash_balance, currency_code"
        "  FROM portfolios WHERE portfolio_id = :pid",
        {"pid": portfolio_id},
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    if int(row["user_id"]) != int(user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your portfolio")
    return row
