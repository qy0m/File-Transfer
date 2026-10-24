import io
import logging
import os
import sqlite3
import time
import zipfile

from contextlib import ExitStack
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .database import connect
from .file_store import open_stored_file, path_parts


router = APIRouter()
ID_PATTERN = r"^[A-Za-z0-9_-]{32}$"


def download_records(transfer_id):
    try:
        with connect() as connection:
            connection.execute("BEGIN")

            transfer = connection.execute(
                "SELECT state, expires_at FROM transfers WHERE id = ?",
                (transfer_id,),
            ).fetchone()

            if transfer is None:
                raise HTTPException(404, "Transfer not found.")

            if transfer[1] <= int(time.time()) or transfer[0] == "expired":
                raise HTTPException(410, "Transfer expired.")

            if transfer[0] != "ready":
                raise HTTPException(404, "Transfer is not ready.")

            rows = connection.execute(
                """
                SELECT f.id, f.original_name, f.size_bytes, f.state,
                        COALESCE(p.relative_path, f.original_name),
                        CASE WHEN l.transfer_id IS NULL
                            THEN f.storage_name ELSE p.relative_path END
                FROM files AS f
                LEFT JOIN file_paths AS p ON p.file_id = f.id
                LEFT JOIN folder_layouts AS l ON l.transfer_id = f.transfer_id
                WHERE f.transfer_id = ?
                ORDER BY f.id
                """,
                (transfer_id,),
            ).fetchall()

        if not rows or any(row[3] != "ready" for row in rows):
            raise HTTPException(503, "Transfer unavailable.")

        return rows

    except sqlite3.Error as error:
        logging.exception("Could not load download metadata.")
        raise HTTPException(
            503,
            "Database unavailable.",
        ) from error

def open_records(transfer_id, rows):
    stack = ExitStack()
    opened = []

    try:
        for row in rows:
            stream = stack.enter_context(
                open_stored_file(transfer_id, row[5])
            )

            if os.fstat(stream.fileno()).st_size != row[2]:
                raise OSError("Stored file size does not match.")

            opened.append((row, stream))

        return stack, opened

    except (OSError, ValueError, TypeError) as error:
        stack.close()
        logging.exception("Could not open download storage.")

        raise HTTPException(
            503,
            "Download storage unavailable.",
        ) from error


def file_chunks(stack, stream, size):
    try:
        remaining = size

        while remaining:
            chunk = stream.read(min(64 * 1024, remaining))

            if not chunk:
                raise OSError("Stored file ended unexpectedly.")

            remaining -= len(chunk)
            yield chunk
    finally:
        stack.close()

class ZipSink(io.RawIOBase):
    def __init__(self):
        super().__init__()
        self.pending = bytearray()
        self.position = 0

    def writable(self):
        return True

    def tell(self):
        return self.position

    def write(self, data):
        self.pending.extend(data)
        self.position += len(data)
        return len(data)

    def take(self):
        data = bytes(self.pending)
        self.pending.clear()
        return data

def zip_chunks(stack, opened, folder):
    sink = ZipSink()
    seen = set()

    prefix = (
        folder.rpartition("/")[0] + "/"
        if folder and "/" in folder
        else ""
    )

    try:
        with zipfile.ZipFile(
            sink,
            "w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as archive:
            for row, stream in opened:
                name = row[4][len(prefix):]
                candidate = name
                number = 2

                # Older transfers could contain duplicate filenames.
                while candidate in seen:
                    path = PurePosixPath(name)


                    candidate = str(
                        path.with_name(
                            f"{path.stem} ({number}){path.suffix}"
                        )
                    )

                    number += 1

                seen.add(candidate)

                with archive.open(
                    candidate,
                    "w",
                    force_zip64=True,
                ) as member:
                    yield sink.take()
                    remaining = row[2]

                    while remaining:
                        chunk = stream.read(
                            min(64 * 1024, remaining)
                        )

                        if not chunk:
                            raise OSError(
                                "Stored file ended unexpectedly."
                            )

                        member.write(chunk)
                        remaining -= len(chunk)
                        yield sink.take()

                yield sink.take()

        yield sink.take()
    
    finally:
        stack.close()


@router.get("/transfers/{transfer_id}/files/{file_id}/download")
def download_file(
    transfer_id: str = Path(pattern=ID_PATTERN),
    file_id: str = Path(pattern=ID_PATTERN),
):
    rows = [
        row
        for row in download_records(transfer_id)
        if row[0] == file_id
    ]

    if not rows:
        raise HTTPException(404, "File not found.")

    stack, opened = open_records(transfer_id, rows)
    row, stream = opened[0]

    return StreamingResponse(
        file_chunks(stack, stream, row[2]),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(row[2]),
            "Content-Disposition":
                "attachment; filename*=UTF-8''" +
                quote(row[1], safe=""),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stack.close),
    )


@router.get("/transfers/{transfer_id}/archive")
def download_archive(
    transfer_id: str = Path(pattern=ID_PATTERN),
    folder: str | None = Query(default=None, max_length=1024),
):
    rows = download_records(transfer_id)

    try:
        if folder is not None:
            path_parts(folder)

            rows = [
                row
                for row in rows
                if row[4].startswith(folder + "/")
            ]
        
        for row in rows:
            path_parts(row[4])

    except (ValueError, TypeError) as error:
        raise HTTPException(
            400,
            "Invalid folder path.",
        ) from error

    if not rows:
        raise HTTPException(404, "Folder not found.")

    stack, opened = open_records(transfer_id, rows)

    if folder:
        archive_name = folder.rsplit("/", 1)[-1]
    else:
        roots = {row[4].split("/", 1)[0] for row in rows}

        if len(roots) == 1 and all("/" in row[4] for row in rows):
            archive_name = next(iter(roots))
        else:
            archive_name = "files"
        
    name = archive_name + ".zip"

    return StreamingResponse(
        zip_chunks(stack, opened, folder),
        media_type="application/zip",
        headers={
            "Content-Disposition":
                "attachment; filename*=UTF-8''" +
                quote(name, safe=""),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stack.close),
    )