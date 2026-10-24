import os
import sqlite3
import time

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


DATABASE_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        "/data/database/transfers.sqlite3",
    )
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS transfers (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK(state IN ('pending', 'ready', 'expired')),
    total_bytes INTEGER NOT NULL DEFAULT 0
        CHECK(total_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    transfer_id TEXT NOT NULL
        REFERENCES transfers(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    storage_name TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL
        CHECK(size_bytes >= 0),
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK(state IN ('pending', 'ready'))
);

CREATE TABLE IF NOT EXISTS upload_progress (
    file_id TEXT PRIMARY KEY
        REFERENCES files(id) ON DELETE CASCADE,
    received_bytes INTEGER NOT NULL DEFAULT 0
        CHECK(received_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS upload_sessions (
    transfer_id TEXT PRIMARY KEY
        REFERENCES transfers(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS transfers_expiration
    ON transfers(expires_at);

CREATE INDEX IF NOT EXISTS files_transfer
    ON files(transfer_id);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS account_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS account_sessions_expiration
    ON account_sessions(expires_at);

CREATE TABLE IF NOT EXISTS transfer_owners (
    transfer_id TEXT PRIMARY KEY
        REFERENCES transfers(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS transfer_owners_user
    ON transfer_owners(user_id);

CREATE TABLE IF NOT EXISTS auth_limits (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    resets_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS guest_transfer_owners (
    transfer_id TEXT PRIMARY KEY
        REFERENCES transfers(id) ON DELETE CASCADE,
    identity_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS guest_transfer_owners_identity
    ON guest_transfer_owners(identity_hash);

CREATE TABLE IF NOT EXISTS file_paths (
    file_id TEXT PRIMARY KEY
        REFERENCES files(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folder_layouts (
    transfer_id TEXT PRIMARY KEY
        REFERENCES transfers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transfer_activity (
    transfer_id TEXT PRIMARY KEY
        REFERENCES transfers(id) ON DELETE CASCADE,
    client_hash TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS transfer_activity_client
    ON transfer_activity(client_hash);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
    )

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)

        # Existing pending uploads receive one inactivity window.
        connection.execute(
            """
            INSERT OR IGNORE INTO transfer_activity
                (transfer_id, client_hash, updated_at)
            SELECT id, 'legacy:' || id, ?
            FROM transfers
            WHERE state = 'pending'
            """,
            (int(time.time()),),
        )


def database_ready() -> bool:
    with connect() as connection:
        connection.execute(
            "SELECT id FROM transfers LIMIT 1"
        ).fetchall()

        connection.execute(
            "SELECT id FROM files LIMIT 1"
        ).fetchall()

        connection.execute(
            "SELECT transfer_id FROM transfer_activity LIMIT 1"
        ).fetchall()

    return True
