"""Manage the single upload administrator from the server terminal only."""

import argparse
import re
import sqlite3
import sys

from .database import DATABASE_PATH, connect


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage an existing account's upload administrator role."
    )

    parser.add_argument("username")

    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--grant", action="store_true")
    actions.add_argument("--revoke", action="store_true")
    actions.add_argument("--status", action="store_true")

    args = parser.parse_args(argv)
    username = args.username.strip().lower()

    if re.fullmatch(r"[a-z0-9_-]{3,32}", username) is None:
        parser.error("Provide a valid account username.")

    if not DATABASE_PATH.is_file():
        parser.error("Database not found. Check DATABASE_PATH.")

    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            user = connection.execute(
                "SELECT id, is_admin FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if user is None:
                raise RuntimeError("Account not found. Register it first.")

            if args.status:
                role = (
                    "upload administrator"
                    if user[1]
                    else "regular account"
                )

                print(f"{username}: {role}.")
                return 0

            enabled = int(args.grant)

            if enabled == user[1]:
                print(f"{username}: role is already set; no changes made.")
                return 0

            other = connection.execute(
                "SELECT 1 FROM users WHERE is_admin = 1 AND id != ?",
                (user[0],),
            ).fetchone()

            if enabled and other:
                raise RuntimeError(
                    "Another administrator exists. Revoke that role first."
                )

            connection.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (enabled, user[0]),
            )

            revoked = connection.execute(
                "DELETE FROM account_sessions WHERE user_id = ?",
                (user[0],),
            ).rowcount

    except (sqlite3.Error, OSError, RuntimeError) as error:
        print(f"Administrator update failed: {error}", file=sys.stderr)
        return 1

    role = "upload administrator" if enabled else "regular account"

    print(f"{username}: {role}.")
    print(f"Revoked {revoked} session(s). Sign in again.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())