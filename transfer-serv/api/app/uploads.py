import asyncio
import hashlib
import hmac
import os
import sqlite3
import time
import logging

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Path as PathParameter,
    Query,
    Request,
)
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .file_store import open_stored_file
from .database import connect
from .storage import UPLOAD_PATH, ensure_free_space, PENDING_IDLE_SECONDS



MAX_CHUNK_BYTES = 8 * 1024 * 1024


ID_PATTERN = r"^[A-Za-z0-9_-]{32}$"

router = APIRouter()



def authorize(connection, transfer_id, token):
    row = connection.execute(
        """
        SELECT t.state, t.expires_at, s.token_hash,
                COALESCE(a.updated_at, t.created_at)
        FROM transfers AS t
        JOIN upload_sessions AS s ON s.transfer_id = t.id
        LEFT JOIN transfer_activity AS a ON a.transfer_id = t.id
        WHERE t.id = ?
        """,
        (transfer_id,),
    ).fetchone()

    supplied_hash = hashlib.sha256(
        (token or "").encode("utf-8")
    ).hexdigest()

    if row is None or not hmac.compare_digest(
        row[2], supplied_hash
    ):
        raise HTTPException(401, "Invalid upload token.")

    if row[1] <= int(time.time()) or row[0] =="expired":
        raise HTTPException(410, "Transfer expired.")

    if (
        row[0] == "pending"
        and row[3] <= int(time.time()) - PENDING_IDLE_SECONDS
    ):
        raise HTTPException(
            410,
            "Inactive upload expired. Start a new transfer.",
        )

    return row[0]


def read_status(transfer_id, token):
    try:
        with connect() as connection:
            state = authorize(connection, transfer_id, token)

            rows = connection.execute(
                """
                SELECT f.id, f.original_name, f.size_bytes,
                       f.state, COALESCE(p.received_bytes, 0)
                FROM files AS f
                LEFT JOIN upload_progress AS p ON p.file_id = f.id
                WHERE f.transfer_id = ?
                ORDER BY f.id
                """,
                (transfer_id,),
            ).fetchall()

        return {
            "id": transfer_id,
            "state": state,
            "files": [
                {
                    "id": row[0],
                    "name": row[1],
                    "size_bytes": row[2],
                    "state": row[3],
                    "received_bytes": row[4],
                }
                for row in rows
            ],
        }
    except sqlite3.Error as error:
        raise HTTPException(
            503, "Database unavailable."
        ) from error


def save_chunk(transfer_id, file_id, token, offset, data):
    try:
        with connect() as connection:
            # Serializes database and file changes across API workers.
            connection.execute("BEGIN IMMEDIATE")

            transfer_state = authorize(
                connection, transfer_id, token
            )

            row = connection.execute(
                """
                SELECT CASE WHEN l.transfer_id IS NULL
                            THEN f.storage_name ELSE fp.relative_path END,
                        f.size_bytes, f.state,
                        COALESCE(p.received_bytes, 0)
                FROM files AS f
                LEFT JOIN upload_progress AS p ON p.file_id = f.id
                LEFT JOIN file_paths AS fp ON fp.file_id = f.id
                LEFT JOIN folder_layouts AS l ON l.transfer_id = f.transfer_id
                WHERE f.id = ? AND f.transfer_id = ?
                """,
                (file_id, transfer_id),
            ).fetchone()

            if row is None:
                raise HTTPException(404, "File not found.")

            storage_name, expected, state, received = row

            if transfer_state != "pending" or state == "ready":
                raise HTTPException(
                    409, "Uploads already complete."
                )

            if offset != received:
                raise HTTPException(
                    409,
                    {
                        "error": "Incorrect offset.",
                        "expected_offset": received,
                    },
                )

            if len(data) > MAX_CHUNK_BYTES:
                raise HTTPException(413, "Chunk exceeds 8 MiB.")

            new_received = received + len(data)

            if new_received > expected:
                raise HTTPException(
                    413, "Chunk exceeds the declared file size."
                )

            if not data and expected != 0:
                raise HTTPException(400, "Chunk cannot be empty.")

            try:
                output = open_stored_file(
                    transfer_id,
                    storage_name,
                    write=True,
                    create=(received == 0),
                )
            except FileNotFoundError as error:
                raise HTTPException(
                    503,
                    "Stored file is missing.",
                ) from error

            with output:

                output.seek(0, os.SEEK_END)

                if output.tell() < received:
                    raise HTTPException(
                        503, "Stored file is shorter than expected."
                    )

                # Discard bytes left by an uncomitted previous write.
                output.truncate(received)
                output.seek(received)

                ensure_free_space(len(data))

                written = output.write(data)

                if written != len(data):
                    raise OSError("Incomplete file write")

                output.flush()
                os.fsync(output.fileno())

            file_state = (
                "ready" if new_received == expected else "pending"
            )

            connection.execute(
                """
                INSERT INTO upload_progress (file_id, received_bytes)
                VALUES (?, ?)
                ON CONFLICT(file_id) DO UPDATE
                SET received_bytes = excluded.received_bytes
                """,
                (file_id, new_received),
            )

            connection.execute(
                "UPDATE files SET state = ? WHERE id = ?",
                (file_state, file_id),
            )

            remaining = connection.execute(
                """
                SELECT COUNT(*) FROM files
                WHERE transfer_id = ? AND state != 'ready'
                """,
                (transfer_id,),
            ).fetchone()[0]

            transfer_state = (
                "ready" if remaining == 0 else "pending"
            )

            connection.execute(
                "UPDATE transfers SET state = ? WHERE id = ?",
                (transfer_state, transfer_id),
            )

            connection.execute(
                """
                UPDATE transfer_activity
                SET updated_at = ?
                WHERE transfer_id = ?
                """,
                (int(time.time()), transfer_id),
            )

        return {
            "file_id": file_id,
            "received_bytes": new_received,
            "file_state": file_state,
            "transfer_state": transfer_state,
        }
    except sqlite3.Error as error:
        logging.exception("Could not save upload chunk.")

        raise HTTPException(
            503, "Database unavailable."
        ) from error
    except OSError as error:
        raise HTTPException(
            507, "Could not write upload storage."
        ) from error


@router.get("/transfers/{transfer_id}/upload-status")
def upload_status(
    transfer_id: str = PathParameter(pattern=ID_PATTERN),
    upload_token: str | None = Header(
        default=None, alias="X-Upload-Token"
    ),
):
    result = read_status(transfer_id, upload_token)

    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store"},
    )

@router.put("/transfers/{transfer_id}/files/{file_id}/chunks")
async def upload_chunk(
    request: Request,
    transfer_id: str = PathParameter(pattern=ID_PATTERN),
    file_id: str = PathParameter(pattern=ID_PATTERN),
    offset: int = Query(ge=0),
    upload_token: str | None = Header(
        default=None, alias="X-Upload-Token"
    ),
):
    # Authenticate before accepting the body; recheck when saving.
    await run_in_threadpool(
        read_status, transfer_id, upload_token
    )

    content_type = request.headers.get("content-type", "")

    if content_type.split(";")[0].strip().lower() != (
        "application/octet-stream"
    ):
        raise HTTPException(
            415, "Use application/octet-stream."
        )

    if request.headers.get(
        "content-encoding", "identity"
    ) != "identity":
        raise HTTPException(
            415, "Compressed chunks are unsupported."
        )

    length = request.headers.get("content-length")

    if length is not None:
        if not length.isascii() or not length.isdigit():
            raise HTTPException(400, "Invalid Content-Length.")

        if int(length) > MAX_CHUNK_BYTES:
            raise HTTPException(413, "Chunk exceeds 8 MiB.")

    data = bytearray()

    try:
        async with asyncio.timeout(130):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_CHUNK_BYTES:
                    raise HTTPException(
                        413, "Chunk exceeds 8 MiB."
                    )

                data.extend(chunk)
    except TimeoutError as error:
        raise HTTPException(
            408, "Chunk upload timed out."
        ) from error
    except ClientDisconnect as error:
        raise HTTPException(
            400, "Upload disconnected."
        ) from error

    result = await run_in_threadpool(
        save_chunk,
        transfer_id,
        file_id,
        upload_token,
        offset,
        bytes(data),
    )

    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store"},
    )
