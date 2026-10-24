import hashlib
import secrets
import sqlite3
import time
import logging
import shutil

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParameter,
    Request,
)

from fastapi.responses import JSONResponse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .auth import (
    optional_user,
    required_user,
    require_same_origin,
    throttle,
)
from .client_identity import client_key

from .file_store import path_parts

from .database import connect
from .uploads import UPLOAD_PATH
from .storage import reserve_capacity
from .storage import reserve_account_capacity
from .storage import reserve_pending_capacity
from .storage import (
    guest_identity,
    reserve_guest_capacity,
    set_guest_cookie,
)


MAX_FILES = 25
MAX_BYTES = 5_000_000_000
TRANSFER_LIFETIME_SECONDS = 24 * 60 * 60

router = APIRouter()


class FileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        strict=True,
        min_length=1,
        max_length=255,
    )

    relative_path: str | None = Field(
        default=None,
        strict=True,
        min_length=1,
        max_length=1024,
    )

    size_bytes: int = Field(
        strict=True,
        ge=0,
        le=MAX_BYTES,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Filename cannot be blank.")

        if "/" in value or "\\" in value:
            raise ValueError("Provide a filename, not a path.")

        if any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError(
                "Filename cannot contain control characters."
            )

        return value
    
    @model_validator(mode="after")
    def validate_relative_path(self):
        if self.relative_path is None:
            return self

        path = self.relative_path
        parts = path.split("/")

        if (
            len(path.encode("utf-8")) > 1024
            or chr(92) in path
            or any(part in ("", ".", "..") for part in parts)
            or any(len(part) > 255 for part in parts)
            or any(
                ord(char) < 32 or ord(char) == 127
                for char in path
            )
            or (
                len(parts[0]) == 2
                and parts[0][0].isalpha()
                and parts[0][1] == ":"
            )
            or parts[-1] != self.name
        ):
            raise ValueError("Invalid folder path.")

        return self

class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[FileRequest] = Field(
        min_length=1,
        max_length=MAX_FILES,
    )

    @model_validator(mode="after")
    def validate_paths(self):
        paths = [
            file.relative_path or file.name
            for file in self.files
        ]

        if len(set(paths)) != len(paths):
            raise ValueError(
                "Each file must have a unique folder path."
            )

        seen = set(paths)

        for path in paths:
            parts = path.split("/")

            for end in range(1, len(parts)):
                if "/".join(parts[:end]) in seen:
                    raise ValueError(
                        "A file cannot also be a folder."
                    )

        return self


@router.post("/transfers", status_code=201)
def create_transfer(
    request: TransferRequest,
    http_request: Request,
):
    total_bytes = sum(
        file.size_bytes
        for file in request.files
    )

    if total_bytes > MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail="The combined size must be 5 GB or less.",
        )

    transfer_id = secrets.token_urlsafe(24)
    upload_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        upload_token.encode("utf-8")
    ).hexdigest()

    created_at = int(time.time())
    expires_at = created_at + TRANSFER_LIFETIME_SECONDS

    files = []

    for file in request.files:
        try:
            path_parts(file.relative_path or file.name)
        except ValueError as error:
            raise HTTPException(
                422,
                "Invalid folder path or filename.",
            ) from error

        file_id = secrets.token_urlsafe(24)

        files.append({
            "id": file_id,
            "name": file.name,
            "relative_path": file.relative_path or file.name,
            "size_bytes": file.size_bytes,
        })

    guest_token = None
    guest_hash = None

    identity = client_key(http_request)
    throttle("create:client:" + identity, 10, 60)

    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            owner = optional_user(connection, http_request)

            reserve_pending_capacity(
                connection,
                identity,
                total_bytes,
            )

            if owner is not None:
                require_same_origin(http_request)

                reserve_account_capacity(
                    connection,
                    owner[0],
                    total_bytes,
                )
            else:
                guest_token, guest_hash = guest_identity(
                    http_request
                )

                reserve_guest_capacity(
                    connection,
                    guest_hash,
                    total_bytes,
                )

            reserve_capacity(connection, total_bytes)

            connection.execute(
                """
                INSERT INTO transfers (
                    id,
                    created_at,
                    expires_at,
                    state,
                    total_bytes
                )
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (
                    transfer_id,
                    created_at,
                    expires_at,
                    total_bytes,
                ),
            )

            connection.execute(
                """
                INSERT INTO transfer_activity
                    (transfer_id, client_hash, updated_at)
                VALUES (?, ?, ?)
                """,
                (transfer_id, identity, created_at),
            )

            if owner is not None:
                connection.execute(
                    """
                    INSERT INTO transfer_owners (
                        transfer_id,
                        user_id
                    )
                    VALUES (?, ?)
                    """,
                    (transfer_id, owner[0]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO guest_transfer_owners (
                        transfer_id,
                        identity_hash
                    )
                    VALUES (?, ?)
                    """,
                    (transfer_id, guest_hash),
                )

            connection.execute(
                """
                INSERT INTO upload_sessions (
                    transfer_id,
                    token_hash
                )
                VALUES (?, ?)
                """,
                (
                    transfer_id,
                    token_hash,
                ),
            )

            connection.executemany(
                """
                INSERT INTO files (
                    id,
                    transfer_id,
                    original_name,
                    storage_name,
                    size_bytes,
                    state
                )
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                [
                    (
                        file["id"],
                        transfer_id,
                        file["name"],
                        file["id"],
                        file["size_bytes"],
                    )
                    for file in files
                ],
            )

            connection.executemany(
                """
                INSERT INTO file_paths (file_id, relative_path)
                VALUES (?, ?)
                """,
                [
                    (file["id"], file["relative_path"])
                    for file in files
                ],
            )

            connection.execute(
                "INSERT INTO folder_layouts (transfer_id) VALUES (?)",
                (transfer_id,),
            )

    except sqlite3.Error as error:
        logging.exception("Could not create the transfer.")

        raise HTTPException(
            status_code=503,
            detail="Could not create the transfer.",
        ) from error

    response = JSONResponse(
        status_code=201,
        headers={
            "Cache-Control": "no-store",
        },
        content={
            "id": transfer_id,
            "upload_token": upload_token,
            "created_at": created_at,
            "expires_at": expires_at,
            "state": "pending",
            "total_bytes": total_bytes,
            "files": files,
        },
    )

    if guest_token is not None:
        set_guest_cookie(response, guest_token)

    return response

@router.get("/transfers/{transfer_id}")
def public_transfer(
    transfer_id: str = PathParameter(
        pattern=r"^[A-Za-z0-9_-]{32}$"
    ),
):
    try:
        with connect() as connection:
            # Read transfer information from one database snapshot.
            connection.execute("BEGIN")

            transfer = connection.execute(
                """
                SELECT created_at, expires_at, state, total_bytes
                FROM transfers
                WHERE id = ?
                """,
                (transfer_id,),
            ).fetchone()

            if transfer is None:
                raise HTTPException(
                    404, "Transfer not found."
                )
            
            created_at, expires_at, state, total_bytes = transfer

            if expires_at <= int(time.time()) or state == "expired":
                raise HTTPException(
                    410, "Transfer expired."
                )

            if state != "ready":
                raise HTTPException(
                    404, "Transfer not available."
                )

            rows = connection.execute(
                """
                SELECT f.id, f.original_name, f.size_bytes, f.state,
                       COALESCE(p.relative_path, f.original_name)
                FROM files AS f
                LEFT JOIN file_paths AS p ON p.file_id = f.id
                WHERE f.transfer_id = ?
                ORDER BY COALESCE(p.relative_path, f.original_name), f.id
                """,
                (transfer_id,),
            ).fetchall()

            if not rows or any(row[3] != "ready" for row in rows):
                raise HTTPException(
                    503, "Transfer unavailable."
                )

    except sqlite3.Error as error:
        logging.exception("Could not load public transfer.")

        raise HTTPException(
            503, "Database unavailable."
        ) from error


    return JSONResponse(
        headers={"Cache-Control": "no-store"},
        content={
            "id": transfer_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "state": "ready",
            "total_bytes": total_bytes,
            "files": [
                {
                    "id": row[0],
                    "name": row[1],
                    "size_bytes": row[2],
                    "relative_path": row[4],
                }
                for row in rows
            ],
        },
    )

@router.delete("/account/transfers/{transfer_id}")
def delete_transfer(
    request: Request,
    transfer_id: str = PathParameter(
        pattern=r"^[A-Za-z0-9_-]{32}$"
    ),
):
    require_same_origin(request)

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

        user = required_user(connection, request)

        owned = connection.execute(
            """
            SELECT 1
            FROM transfers AS t
            JOIN transfer_owners AS o ON o.transfer_id = t.id
            WHERE t.id = ? AND o.user_id = ?
            """,
            (transfer_id, user[0]),
        ).fetchone()

        if owned is None:
            raise HTTPException(404, "Transfer not found.")

        # Comit revocation before attempting filesystem removal.
        connection.execute(
            """
            UPDATE transfers
            SET state = 'expired',
                expires_at = MIN(expires_at, ?)
            WHERE id = ?
            """,
            (int(time.time()), transfer_id),
        )

        connection.execute(
            "DELETE FROM upload_sessions WHERE transfer_id = ?",
            (transfer_id,),
        )

    storage_deleted = False

    try:
        with connect() as connection:
            # Same lock used by chunk writes and automatic cleanup.
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                "SELECT state FROM transfers WHERE id = ?",
                (transfer_id,),
            ).fetchone()

            if row is not None:
                if row[0] != "expired":
                    raise HTTPException(
                        409,
                        "Transfer state changed.",
                    )

                directory = UPLOAD_PATH.resolve() / transfer_id

                if directory.is_symlink():
                    directory.unlink()
                elif directory.exists():
                    if not directory.is_dir():
                        raise OSError(
                            "Trasnfer storage is not a directory."
                        )

                    if not shutil.rmtree.avoids_symlink_attacks:
                        raise OSError(
                            "Safe directory removal is unavailable."
                        )

                    shutil.rmtree(directory)

                connection.execute(
                    "DELETE FROM transfers WHERE id = ?",
                    (transfer_id,),
                )

        storage_deleted = True

    except (OSError, sqlite3.Error):
        logging.exception(
            "Transfer %s disabled; storage deletion will retry.",
            transfer_id,
        )

    return JSONResponse(
        status_code=200 if storage_deleted else 202,
        headers={"Cache-Control": "no-store"},
        content={
            "ok": True,
            "storage_deleted": storage_deleted,
        },
    )