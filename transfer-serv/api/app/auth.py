import hashlib
import os
import re
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .database import connect
from .storage import storage_summary
from .storage import (
    guest_identity,
    guest_storage_summary,
    set_guest_cookie,
)

from .client_identity import client_key

router = APIRouter()

COOKIE_NAME = "transfer_session"
SESSION_SECONDS = 7 * 24 * 60 * 60

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

APP_ORIGIN = os.environ.get(
    "APP_ORIGIN",
    "http://127.0.0.1:8080",
).rstrip("/")

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))

class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        strict=True,
        min_length=3,
        max_length=32,
    )

    password: str = Field(
        strict=True,
        min_length=12,
        max_length=128,
        repr=False,
    )

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.lower()

        if re.fullmatch(r"[a-z0-9_-]{3,32}", value) is None:
            raise ValueError(
                "Use 3-32 letters, numbers, underscores, or hyphens."
            )

        return value

def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")

    if origin is not None:
        if origin != APP_ORIGIN:
            raise HTTPException(
                403,
                "Request origin is not allowed.",
            )
        return

    # Command-line clients explicitly identify these requests.
    if request.headers.get("x-requested-with") != "transfer-serv":
        raise HTTPException(
            403,
            "Missing request origin or guard header.",
        )

def optional_user(connection, request: Request):
    token = request.cookies.get(COOKIE_NAME)

    if token is None:
        return None

    if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        request.state.clear_account_cookie = True
        return None

    user = connection.execute(
        """
        SELECT u.id, u.username
        FROM account_sessions AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires_at > ?
        """,
        (digest(token), int(time.time())),
    ).fetchone()

    if user is None:
        request.state.clear_account_cookie = True
        return None

    return user

def required_user(connection, request: Request):
    user = optional_user(connection, request)

    if user is None:
        raise HTTPException(
            401,
            "Sign in to access your account.",
        )
    
    return user


def throttle(bucket: str, limit: int, seconds: int) -> None:
    now = int(time.time())
    retry = 0

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            "DELETE FROM auth_limits WHERE resets_at <= ?",
            (now,),
        )

        connection.execute(
            "DELETE FROM account_sessions WHERE expires_at <= ?",
            (now,),
        )

        row = connection.execute(
            """
            SELECT attempts, resets_at
            FROM auth_limits
            WHERE bucket = ?
            """,
            (bucket,),
        ).fetchone()

        if row is None:
            connection.execute(
                "INSERT INTO auth_limits VALUES (?, 1, ?)",
                (bucket, now + seconds),
            )
        elif row[0] >= limit:
            retry = max(1, row[1] - now)
        else:
            connection.execute(
                """
                UPDATE auth_limits
                SET attempts = attempts + 1
                WHERE bucket = ?
                """,
                (bucket,),
            )

    if retry:
        raise HTTPException(
            429,
            "Too many account requests. Try again later.",
            headers={"Retry-After": str(retry)},
        )


def issue_session(
    connection,
    user,
    request: Request,
    status: int = 200,
):
    old_token = request.cookies.get(COOKIE_NAME)

    if old_token:
        connection.execute(
            "DELETE FROM account_sessions WHERE token_hash = ?",
            (digest(old_token),),
        )
    
    token = secrets.token_urlsafe(32)

    connection.execute(
        "INSERT INTO account_sessions VALUES (?, ?, ?)",
        (
            digest(token),
            user[0],
            int(time.time()) + SESSION_SECONDS,
        ),
    )

    response = JSONResponse(
        status_code=status,
        headers={"Cache-Control": "no-store"},
        content={
            "user": {
                "id": user[0],
                "username": user[1],
            },
        },
    )

    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_SECONDS,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )

    return response

@router.post("/auth/register")
def register(credentials: Credentials, request: Request):
    require_same_origin(request)
    throttle("register:client:" + client_key(request), 10, 60)

    password_hash = hasher.hash(credentials.password)

    user = (
        secrets.token_urlsafe(24),
        credentials.username,
    )

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        exists = connection.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (credentials.username,),
        ).fetchone()

        if exists:
            raise HTTPException(
                409,
                "Username is unavailable.",
            )

        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (*user, password_hash, int(time.time())),
        )

        response = issue_session(
            connection,
            user,
            request,
            201,
        )

    return response


@router.post("/auth/login")
def login(credentials: Credentials, request: Request):
    require_same_origin(request)

    throttle("login:client:" + client_key(request), 30, 60)
    throttle("login:" + credentials.username, 10, 600)

    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = ?
            """,
            (credentials.username,),
        ).fetchone()

    try:
        hasher.verify(
            row[2] if row else DUMMY_HASH,
            credentials.password,
        )
    except (VerificationError, InvalidHashError):
        raise HTTPException(
            401,
            "Incorrect username or password.",
        ) from None

    if row is None:
        raise HTTPException(
            401,
            "Incorrect username or password.",
        )

    replacement_hash = (
        hasher.hash(credentials.password)
        if hasher.check_needs_rehash(row[2])
        else None
    )

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        current = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (row[0],),
        ).fetchone()

        if current is None or current[0] != row[2]:
            raise HTTPException(
                401,
                "Account changed. Sign in again.",
            )

        if replacement_hash:
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (replacement_hash, row[0]),
            )

        response = issue_session(
            connection,
            row,
            request,
        )

    return response

@router.post("/auth/logout")
def logout(request: Request):
    require_same_origin(request)

    token = request.cookies.get(COOKIE_NAME)

    if token:
        with connect() as connection:
            connection.execute(
                "DELETE FROM account_sessions WHERE token_hash = ?",
                (digest(token),),
            )

    response = JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={"ok": True},
    )

    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )

    return response


@router.get("/auth/me")
def me(request: Request):
    with connect() as connection:
        user = required_user(connection, request)

    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={
            "user": {
                "id": user[0],
                "username": user[1],
            },
        },
    )

@router.get("/account/transfers")
def account_transfers(
    request: Request,
    page: int = Query(default=1, ge=1, le=1_000_000),
):
    page_size = 25

    with connect() as connection:
        connection.execute("BEGIN")

        user = required_user(connection, request)
        now = int(time.time())
        parameters = (user[0], now)

        total = connection.execute(
            """
            SELECT COUNT(*)
            FROM transfers AS t
            JOIN transfer_owners AS o ON o.transfer_id = t.id
            WHERE o.user_id = ? AND t.expires_at > ?
                AND t.state IN ('pending', 'ready')
            """,
            parameters,
        ).fetchone()[0]

        rows = connection.execute(
            """
            SELECT
                t.id,
                t.created_at,
                t.expires_at,
                t.state,
                t.total_bytes
            FROM transfers AS t
            JOIN transfer_owners AS o ON o.transfer_id = t.id
            WHERE o.user_id = ? AND t.expires_at > ?
                AND t.state IN ('pending', 'ready')
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT ? OFFSET ?
            """,
            (
                *parameters,
                page_size,
                (page - 1) * page_size,
            ),
        ).fetchall()

        transfers = []

        for row in rows:
            files = connection.execute(
                """
                SELECT
                    f.id,
                    f.original_name,
                    f.size_bytes,
                    f.state,
                    COALESCE(p.received_bytes, 0)
                FROM files AS f
                LEFT JOIN upload_progress AS p
                    ON p.file_id = f.id
                WHERE f.transfer_id = ?
                ORDER BY f.id
                """,
                (row[0],),
            ).fetchall()

            transfers.append({
                "id": row[0],
                "created_at": row[1],
                "expires_at": row[2],
                "state": row[3],
                "total_bytes": row[4],
                "share_path": (
                    "/transfer.php?id=" + row[0]
                    if row[3] == "ready"
                    else None
                ),
                "files": [
                    {
                        "id": file[0],
                        "name": file[1],
                        "size_bytes": file[2],
                        "state": file[3],
                        "received_bytes": file[4],
                    }
                    for file in files
                ],
            })

    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={
            "transfers": transfers,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": page * page_size < total,
        },
    )

class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(
        strict=True,
        min_length=1,
        max_length=128,
        repr=False,
    )

    new_password: str = Field(
        strict=True,
        min_length=12,
        max_length=128,
        repr=False,
    )

@router.get("/account/storage")
def account_storage(request: Request):
    with connect() as connection:
        connection.execute("BEGIN")

        user = required_user(connection, request)

        result = storage_summary(connection, user[0])

    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content=result,
    )

@router.post("/account/password")
def change_password(
    body: PasswordChange,
    request: Request,
):
    require_same_origin(request)

    with connect() as connection:
        user = required_user(connection, request)

        old_hash = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user[0],),
        ).fetchone()[0]

    throttle("password:client:" + client_key(request), 20, 60)
    throttle("password:" + user[0], 5, 600)

    try:
        hasher.verify(old_hash, body.current_password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(
            400,
            "Current password is incorrect.",
        ) from None

    if body.new_password == body.current_password:
        raise HTTPException(
            400,
            "Choose a different new password.",
        )
    
    new_hash = hasher.hash(body.new_password)

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        user = required_user(connection, request)

        updated = connection.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ? AND password_hash = ?
            """,
            (new_hash, user[0], old_hash),
        )

        if updated.rowcount != 1:
            raise HTTPException(
                409,
                "Account changed. Sign in again.",
            )

        connection.execute(
            "DELETE FROM account_sessions WHERE user_id = ?",
            (user[0],),
        )

    response = JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={"ok": True},
    )

    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )

    return response

@router.get("/guest/storage")
def guest_storage(request: Request):
    token, identity_hash = guest_identity(request)

    with connect() as connection:
        connection.execute("BEGIN")

        result = guest_storage_summary(
            connection,
            identity_hash,
        )

    response = JSONResponse(
        headers={"Cache-Control": "no-store"},
        content=result,
    )

    set_guest_cookie(response, token)

    return response