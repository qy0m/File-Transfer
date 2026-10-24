import os
import shutil
import sqlite3
import hashlib
import re
import secrets

from pathlib import Path

from fastapi import HTTPException

def read_limit(
    name: str,
    default: int,
    minimum: int,
) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(
            f"{name} must be a whole number."
        ) from error
    
    if value < minimum or value > 9_223_372_036_854_775_807:
        raise RuntimeError(
            f"{name} must be between {minimum} "
            "and 9223372036854775807."
        )

    return value

UPLOAD_PATH = Path(
    os.environ.get("UPLOAD_PATH", "/data/uploads")
)

MAX_STORAGE_BYTES = read_limit(
    "MAX_STORAGE_BYTES",
    100_000_000_000,
    1,
)

MIN_FREE_DISK_BYTES = read_limit(
    "MIN_FREE_DISK_BYTES",
    5_000_000_000,
    0,
)

MAX_STORED_TRANSFERS = read_limit(
    "MAX_STORED_TRANSFERS",
    10_000,
    1,
)

PENDING_IDLE_SECONDS = 15 * 60
MAX_PENDING_PER_CLIENT = 3
MAX_PENDING_BYTES_PER_CLIENT = 5_000_000_000


def reserve_pending_capacity(
    connection,
    identity: str,
    total_bytes: int,
) -> None:
    # Caller holds BEGIN IMMEDIATE until the reservation is inserted.
    count, reserved = connection.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(t.total_bytes), 0)
        FROM transfers AS t
        JOIN transfer_activity AS a ON a.transfer_id = t.id
        WHERE a.client_hash = ? AND t.state = 'pending'
        """,
        (identity,),
    ).fetchone()

    if count >= MAX_PENDING_PER_CLIENT or (
        total_bytes > MAX_PENDING_BYTES_PER_CLIENT - reserved
    ):
        raise HTTPException(
            429,
            "This connection already has pending uploads. "
            "Finish or delete them, or wait for inactive uploads to expire.",
            headers={"Retry-After": "60"},
        )

def ensure_free_space(additional_bytes: int) -> None:
    try:
        UPLOAD_PATH.mkdir(
            parents=True,
            exist_ok=True,
        )

        free = shutil.disk_usage(UPLOAD_PATH).free

    except OSError as error:
        raise HTTPException(
            507,
            "Upload storage is unavailable.",
        ) from error

    if free < MIN_FREE_DISK_BYTES + additional_bytes:
        raise HTTPException(
            507,
            "Upload storage is low on free space. "
            "Try again after files are removed.",
        )

def reserve_capacity(
    connection: sqlite3.Connection,
    total_bytes: int,
) -> None:
    # Caller must hold BEGIN IMMEDIATE through transfer insertion.
    reserved, count = connection.execute(
        """
        SELECT COALESCE(SUM(total_bytes), 0), COUNT(*)
        FROM transfers
        """
    ).fetchone()

    if count >= MAX_STORED_TRANSFERS:
        raise HTTPException(
            507,
            "Transfer capacity reached. "
            "Try again after transfers are removed.",
        )
    
    if total_bytes > MAX_STORAGE_BYTES - reserved:
        raise HTTPException(
            507,
            "Storage capacity reached. "
            "Try again after transfers are removed.",
        )

    outstanding = connection.execute(
        """
        SELECT COALESCE(
            SUM(MAX(
                f.size_bytes - COALESCE(p.received_bytes, 0),
                0
            )),
            0
        )
        FROM files AS f
        LEFT JOIN upload_progress AS p ON p.file_id = f.id
        WHERE f.state = 'pending'
        """
    ).fetchone()[0]

    ensure_free_space(outstanding + total_bytes)

ACCOUNT_STORAGE_BYTES = 5_000_000_000


def account_reserved_bytes(
    connection: sqlite3.Connection,
    user_id: str,
) -> int:
    return connection.execute(
        """
        SELECT COALESCE(SUM(t.total_bytes), 0)
        FROM transfers AS t
        JOIN transfer_owners AS o ON o.transfer_id = t.id
        WHERE o.user_id = ?
        """,
        (user_id,),
    ).fetchone()[0]


def reserve_account_capacity(
    connection: sqlite3.Connection,
    user_id: str,
    additional_bytes: int,
) -> None:
    # Call inside BEGIN IMMEDIATE, before inserting the transfer.
    used = account_reserved_bytes(connection, user_id)

    if additional_bytes > max(0, ACCOUNT_STORAGE_BYTES - used):
        raise HTTPException(
            status_code=507,
            detail=(
                "Your account has reached its 5 GB storage allowance. "
                "Delete uploads or choose smaller files."
            ),
        )


def storage_summary(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict:
    used = account_reserved_bytes(connection, user_id)

    return {
        "budget_bytes": ACCOUNT_STORAGE_BYTES,
        "reserved_bytes": used,
        "available_bytes": max(0, ACCOUNT_STORAGE_BYTES - used),
        "account_reserved_bytes": used,
        "reason": "budget" if used >= ACCOUNT_STORAGE_BYTES else None,
    }

GUEST_COOKIE_NAME = "transfer_guest"
GUEST_STORAGE_BYTES = 5_000_000_000


def guest_identity(request):
    token = request.cookies.get(GUEST_COOKIE_NAME)

    if (
        not isinstance(token, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None
    ):
        token = secrets.token_urlsafe(32)

    identity_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    return token, identity_hash


def set_guest_cookie(response, token: str) -> None:
    response.set_cookie(
        key=GUEST_COOKIE_NAME,
        value=token,
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "0") == "1",
        samesite="lax",
        path="/",
    )


def guest_reserved_bytes(
    connection: sqlite3.Connection,
    identity_hash: str,
) -> int:
    return connection.execute(
        """
        SELECT COALESCE(SUM(t.total_bytes), 0)
        FROM transfers AS t
        JOIN guest_transfer_owners AS g ON g.transfer_id = t.id
        WHERE g.identity_hash = ?
        """,
        (identity_hash,),
    ).fetchone()[0]


def reserve_guest_capacity(
    connection: sqlite3.Connection,
    identity_hash: str,
    additional_bytes: int,
) -> None:
    # Caller holds BEGIN IMMEDIATE until the transfer is inserted.
    used = guest_reserved_bytes(connection, identity_hash)

    if additional_bytes > max(0, GUEST_STORAGE_BYTES - used):
        raise HTTPException(
            status_code=507,
            detail=(
                "This guest browser has reached its 5 GB storage allowance. "
                "Try again after its uploads expire."
            ),
        )


def guest_storage_summary(
    connection: sqlite3.Connection,
    identity_hash: str,
) -> dict:
    used = guest_reserved_bytes(connection, identity_hash)

    return {
        "budget_bytes": GUEST_STORAGE_BYTES,
        "reserved_bytes": used,
        "available_bytes": max(0, GUEST_STORAGE_BYTES - used),
        "reason": "budget" if used >= GUEST_STORAGE_BYTES else None,
    }