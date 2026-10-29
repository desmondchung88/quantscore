"""Registration, login and session identity."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.security import (create_access_token, current_user, hash_password,
                               verify_password)
from app.db import mongo, mysql
from app.schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    try:
        user_id = mysql.insert_returning_id(
            "INSERT INTO users (username, email, password_hash)"
            " VALUES (:u, :e, :p)",
            {"u": payload.username, "e": payload.email,
             "p": hash_password(payload.password)},
        )
    except (IntegrityError, DBAPIError) as exc:
        text = str(exc)
        if "uq_username" in text:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "That username is taken")
        if "uq_email" in text:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "That email is already registered")
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Could not create the account")

    # Give every new account a starting portfolio and watchlist.
    mysql.execute(
        "INSERT INTO portfolios (user_id, name, initial_cash, cash_balance)"
        " VALUES (:u, 'My Portfolio', 100000, 100000)", {"u": user_id})
    mysql.execute(
        "INSERT INTO watchlists (user_id, name) VALUES (:u, 'Watchlist')",
        {"u": user_id})

    mongo.log_activity(user_id, "auth.register", {"username": payload.username})
    return {
        "access_token": create_access_token(user_id, payload.username),
        "token_type": "bearer",
        "user": {"user_id": user_id, "username": payload.username,
                 "email": payload.email},
    }


@router.post("/login")
def login(payload: LoginRequest):
    user = mysql.query_one(
        "SELECT user_id, username, email, password_hash FROM users"
        " WHERE username = :u OR email = :u",
        {"u": payload.username.strip()},
    )
    # Same response whether the user is missing or the password is wrong.
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Incorrect username or password")

    mongo.log_activity(user["user_id"], "auth.login", {})
    return {
        "access_token": create_access_token(user["user_id"], user["username"]),
        "token_type": "bearer",
        "user": {"user_id": user["user_id"], "username": user["username"],
                 "email": user["email"]},
    }


@router.get("/me")
def me(user: dict = Depends(current_user)):
    stats = mysql.query_one(
        "SELECT (SELECT COUNT(*) FROM portfolios WHERE user_id = :u) AS portfolios,"
        "       (SELECT COUNT(*) FROM watchlists WHERE user_id = :u) AS watchlists,"
        "       (SELECT COUNT(*) FROM transactions t"
        "          JOIN portfolios p ON p.portfolio_id = t.portfolio_id"
        "         WHERE p.user_id = :u) AS trades",
        {"u": user["user_id"]},
    )
    return {"user": user, "stats": stats}
