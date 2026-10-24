import argparse
import asyncio
import json
import logging
import re
import shutil
import sqlite3
import time

from .database import connect
from .uploads import UPLOAD_PATH
from .storage import PENDING_IDLE_SECONDS

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32}$")
CLEANUP_INTERVAL_SECONDS = 60

def cleanup_once(*, dry_run: bool = False) -> dict:
    now = int(time.time())

    with connect() as connection:
        candidates = connection.execute(
            """
            SELECT t.id
            FROM transfers AS t
            LEFT JOIN transfer_activity AS a ON a.transfer_id = t.id
            WHERE t.expires_at <= ? OR t.state = 'expired'
                OR (
                    t.state = 'pending'
                    AND COALESCE(a.updated_at, t.created_at) <= ?
                )
            ORDER BY t.expires_at, t.id
            LIMIT 100
            """,
            (now, now - PENDING_IDLE_SECONDS),
        ).fetchall()

    result = {
        "dry_run": dry_run,
        "expired_ids": [row[0] for row in candidates],
        "deleted": 0,
        "failed": 0,
    }

    if dry_run:
        return result

    root = UPLOAD_PATH.resolve()

    for (transfer_id,) in candidates:
        try:
            if ID_PATTERN.fullmatch(transfer_id) is None:
                raise ValueError("Invalid transfer ID in database.")

            with connect() as connection:
                # Uploads take this same lock before writing a chunk.
                connection.execute("BEGIN IMMEDIATE")

                transfer = connection.execute(
                    """
                    SELECT t.expires_at, t.state,
                            COALESCE(a.updated_at, t.created_at)
                    FROM transfers AS t
                    LEFT JOIN transfer_activity AS a
                        ON a.transfer_id = t.id
                    WHERE t.id = ?
                    """,
                    (transfer_id,),
                ).fetchone()

                if transfer is None:
                    continue
                
                inactive = (
                    transfer[1] == "pending"
                    and transfer[2]
                    <= int(time.time()) - PENDING_IDLE_SECONDS
                )

                if (
                    transfer[0] > int(time.time())
                    and transfer[1] != "expired"
                    and not inactive
                ):
                    continue

                directory = root / transfer_id

                # Delete a symlink itself without following its target.
                if directory.is_symlink():
                    directory.unlink()
                elif directory.exists():
                    if not directory.is_dir():
                        raise OSError(
                            "Transfer storage is not a directory."
                        )

                    if not shutil.rmtree.avoids_symlink_attacks:
                        raise OSError(
                            "Safe directory cleanup is unavailable."
                        )

                    shutil.rmtree(directory)

                # Cascading foreign keys remove associated records.
                connection.execute(
                    "DELETE FROM transfers WHERE id = ?",
                    (transfer_id,),
                )

            result["deleted"] += 1

        except (OSError, sqlite3.Error, ValueError):
            result["failed"] += 1
            logging.exception(
                "Could not clean up transfer %s.",
                transfer_id,
            )

    return result

async def cleanup_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(cleanup_once)

            if result["deleted"] or result["failed"]:
                logging.info("Transfer cleanup: %s", result)

        except Exception:
            logging.exception(
                "Transfer cleanup failed; it will retry."
            )

        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=CLEANUP_INTERVAL_SECONDS,
            )
        except TimeoutError:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean up expired transfers."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List expired transfers without deleting anything.",
    )

    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    summary = cleanup_once(dry_run=arguments.dry_run)
    print(json.dumps(summary, indent=2))

    raise SystemExit(1 if summary["failed"] else 0)