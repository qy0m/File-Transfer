"""Abuse reports with optional descriptions and terminal-only moderation."""
import argparse
import json
import re
import secrets
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import require_same_origin, throttle
from .client_identity import client_key
from .database import connect

router = APIRouter()
RETENTION_SECONDS = 30 * 24 * 60 * 60


class AbuseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfer_id: str = Field(
        strict=True,
        pattern=r"^[A-Za-z0-9_-]{32}$",
    )
    category: Literal[
        "malware", "phishing", "illegal", "privacy", "indecent", "copyright", "other"
    ]

    description: str = Field(default="", strict=True, max_length=2000)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if re.search(r"[?#&]\s*key\s*=", value, re.IGNORECASE):
            raise ValueError("Remove decryption keys from the description.")
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Unsupported control character in description.")
        return value


@router.post("/abuse/reports")
def submit_report(body: AbuseReport, request: Request):
    require_same_origin(request)
    identity = client_key(request)
    throttle("abuse:client:" + identity, 5, 3600)
    now = int(time.time())

    with connect() as connection:
        transfer = connection.execute(
            "SELECT 1 FROM transfers WHERE id = ? "
            "AND state = 'ready' AND expires_at > ?",
            (body.transfer_id, now),
        ).fetchone()

    if transfer is None:
        raise HTTPException(404, "Transfer unavailable or expired.")

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM abuse_reports WHERE created_at < ?",
            (now - RETENTION_SECONDS,),
        )

        duplicate = connection.execute(
            "SELECT 1 FROM abuse_reports "
            "WHERE transfer_id = ? AND reporter_hash = ?",
            (body.transfer_id, identity),
        ).fetchone()

        if duplicate is None:
            recent = connection.execute(
                "SELECT COUNT(*) FROM abuse_reports WHERE created_at >= ?",
                (now - 86400,),
            ).fetchone()[0]

            if recent >= 200:
                raise HTTPException(
                    429,
                    "Reporting is busy. Try again later.",
                    headers={"Retry-After": "3600"},
                )

            count = connection.execute(
                "SELECT COUNT(*) FROM abuse_reports"
            ).fetchone()[0]

            if count >= 10000:
                raise HTTPException(
                    503, "Reporting is temporarily unavailable."
                )

        connection.execute(
            "INSERT OR IGNORE INTO abuse_reports "
            "(id, transfer_id, category, description, reporter_hash, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open')",
            (
                secrets.token_urlsafe(24),
                body.transfer_id,
                body.category,
                body.description,
                identity,
                now,
            ),
        )

    return JSONResponse(
        status_code=202,
        headers={"Cache-Control": "no-store"},
        content={"ok": True},
    )


def main():
    parser = argparse.ArgumentParser(
        description="Review reports and revoke transfers locally."
    )
    commands = parser.add_subparsers(dest="action", required=True)

    commands.add_parser(
        "list",
        help="Show the latest 50 open reports from the last 30 days.",
    )
    commands.add_parser(
        "show",
        help="Show one report, including its optional description.",
    ).add_argument("id")
    commands.add_parser(
        "disable",
        help="Block new downloads/uploads for a transfer.",
    ).add_argument("id")
    commands.add_parser(
        "resolve",
        help="Close a report without disabling a transfer.",
    ).add_argument("id")

    args = parser.parse_args()

    if (
        args.action != "list"
        and re.fullmatch(r"[A-Za-z0-9_-]{32}", args.id) is None
    ):
        parser.error("Provide a 32-character transfer or report ID.")

    now = int(time.time())

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM abuse_reports WHERE created_at < ?",
            (now - RETENTION_SECONDS,),
        )

        if args.action == "list":
            rows = connection.execute(
                "SELECT id, transfer_id, category, created_at "
                "FROM abuse_reports WHERE status = 'open' "
                "ORDER BY created_at DESC, id LIMIT 50"
            ).fetchall()

            print("REPORT_ID TRANSFER_ID CATEGORY CREATED_UTC")

            for row in rows:
                created = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(row[3]),
                )
                print(row[0], row[1], row[2], created)

            print(
                f"{len(rows)} report(s). "
                "Reports alone do not trigger removal."
            )

        elif args.action == "show":
            row = connection.execute(
                "SELECT transfer_id, category, created_at, description "
                "FROM abuse_reports WHERE id = ?",
                (args.id,),
            ).fetchone()
            if row is None:
                print("Report not found or expired.")
            else:
                print("REPORT_ID", args.id)
                print("TRANSFER_ID", row[0])
                print("CATEGORY", row[1])
                print("CREATED_UTC", time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[2])
                ))
                # Escape control characters and Unicode for safe terminal output.
                print("DESCRIPTION", json.dumps(row[3], ensure_ascii=True))

        elif args.action == "resolve":
            result = connection.execute(
                "UPDATE abuse_reports SET status = 'resolved' WHERE id = ?",
                (args.id,),
            )
            print(
                "Report resolved."
                if result.rowcount
                else "Report not found."
            )

        else:
            result = connection.execute(
                "UPDATE transfers SET state = 'expired', "
                "expires_at = MIN(expires_at, ?) WHERE id = ?",
                (now, args.id),
            )
            connection.execute(
                "DELETE FROM upload_sessions WHERE transfer_id = ?",
                (args.id,),
            )
            connection.execute(
                "UPDATE abuse_reports set status = 'resolved' "
                "WHERE transfer_id = ?",
                (args.id,),
            )
            print(
                "Transfer disabled. Automatic cleanup will remove "
                "stored files. Downloads already in progress may finish."
                if result.rowcount
                else "Transfer not found or already removed."
            )

if __name__ == "__main__":
    main()