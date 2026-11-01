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
            AND NOT EXISTS (
                SELECT 1
                FROM transfer_owners AS o
                JOIN users AS u ON u.id = o.user_id
                WHERE o.transfer_id = t.id AND u.is_admin = 1
            )
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
    *,
    is_admin: bool = False,
) -> None:
    # Caller holds BEGIN IMMEDIATE until transfer insertion.
    reserved, count = connection.execute(
        """
        SELECT COALESCE(SUM(
            CASE WHEN COALESCE(u.is_admin, 0) = 0
                THEN t.total_bytes ELSE 0 END
        ), 0), COUNT(*)
        FROM transfers AS t
        LEFT JOIN transfer_owners AS o ON o.transfer_id = t.id
        LEFT JOIN users AS u ON u.id = o.user_id
        """
    ).fetchone()

    if count >= MAX_STORED_TRANSFERS:
        raise HTTPException(
            507,
            "Transfer capacity reached. "
            "Try again after transfers are removed.",
        )

    if not is_admin and total_bytes > MAX_STORAGE_BYTES - reserved:
        raise HTTPException(
            507,
            "Storage capacity reached. "
            "Try again after transfers are removed.",
        )

    ensure_free_space(pending_bytes(connection) + total_bytes)

def pending_bytes(connection: sqlite3.Connection) -> int:
    return connection.execute(
        """
        SELECT COALESCE(
            SUM(
                MAX(
                    f.size_bytes - COALESCE(p.received_bytes, 0),
                    0
                )
            ),
            0
        )
        FROM files AS f
        LEFT JOIN upload_progress AS p ON p.file_id = f.id
        WHERE f.state = 'pending'
        """
    ).fetchone()[0]

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

    is_admin = bool(
        connection.execute(
            "SELECT is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()[0]
    )

    if is_admin:
        try:
            free = shutil.disk_usage(UPLOAD_PATH).free
        except OSError as error:
            raise HTTPException(
                507,
                "Upload storage is unavailable.",
            ) from error

        available = max(
            0,
            free - MIN_FREE_DISK_BYTES - pending_bytes(connection),
        )

        return {
            "quota_exempt": True,
            "budget_bytes": None,
            "reserved_bytes": used,
            "available_bytes": available,
            "account_reserved_bytes": used,
            "reason": "disk_space" if available == 0 else None,
        }

    return {
        "quota_exempt": False,
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

# Limits shared across guest sessions and regular accounts on one public IP.
MAX_ACTIVE_BYTES_PER_CLIENT = read_limit(
    "MAX_ACTIVE_BYTES_PER_CLIENT", 10_000_000_000, 1
)
MAX_DAILY_BYTES_PER_CLIENT = read_limit(
    "MAX_DAILY_BYTES_PER_CLIENT", 20_000_000_000, 1
)
MAX_DAILY_TRANSFERS_PER_CLIENT = read_limit(
    "MAX_DAILY_TRANSFERS_PER_CLIENT", 100, 1
)


def reserve_client_capacity(connection, identity, total_bytes, now):
    # Caller holds BEGIN IMMEDIATE through transfer creation.
    used = connection.execute(
        """
        SELECT COALESCE(SUM(t.total_bytes), 0)
        FROM transfers AS t
        JOIN transfer_activity AS a ON a.transfer_id = t.id
        WHERE a.client_hash = ? AND NOT EXISTS (
            SELECT 1 FROM transfer_owners AS o
            JOIN users AS u ON u.id = o.user_id
            WHERE o.transfer_id = t.id AND u.is_admin = 1
        )
        """,
        (identity,),
    ).fetchone()[0]

    if total_bytes > max(0, MAX_ACTIVE_BYTES_PER_CLIENT - used):
        raise HTTPException(
            429,
            "This connection has reached its shared upload storage allowance. "
            "Remove existing uploads or wait for them to expire.",
            headers={"Retry-After": "60"},
        )

    row = connection.execute(
        "SELECT reserved_bytes, transfers_created, resets_at "
        "FROM client_upload_budgets WHERE client_hash = ?",
        (identity,),
    ).fetchone()

    charged, count, resets = (
        row if row and row[2] > now else (0, 0, now + 86400)
    )

    if (
        total_bytes > max(0, MAX_DAILY_BYTES_PER_CLIENT - charged)
        or count >= MAX_DAILY_TRANSFERS_PER_CLIENT
    ):
        raise HTTPException(
            429,
            "This connection has reached its daily upload allowance. "
            "Try again later.",
            headers={"Retry-After": str(max(1, resets - now))},
        )

    connection.execute(
        """
        INSERT INTO client_upload_budgets
            (client_hash, reserved_bytes, transfers_created, resets_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(client_hash) DO UPDATE SET
            reserved_bytes = excluded.reserved_bytes,
            transfers_created = excluded.transfers_created,
            resets_at = excluded.resets_at
        """,
        (identity, charged + total_bytes, count + 1, resets),
    )

