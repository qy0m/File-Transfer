import argparse
import getpass
import re
import sqlite3
import sys

from argon2 import PasswordHasher

from .database import DATABASE_PATH, connect


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset an account password and revoke its sessions."
    )
    parser.add_argument("username")
    arguments = parser.parse_args(argv)

    username = arguments.username.strip().lower()

    if re.fullmatch(r"[a-z0-9_-]{3,32}", username) is None:
        parser.error("Provide a valid account username.")

    if not sys.stdin.isatty():
        parser.error("Run this command in an interactive terminal.")

    if not DATABASE_PATH.is_file():
        parser.error(f"Database not found: {DATABASE_PATH}")

    try:
        with connect() as connection:
            user = connection.execute(
                """
                SELECT id, password_hash
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

        if user is None:
            parser.error("Account not found.")

        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm new password: ")

        if not 12 <= len(password) <= 128:
            parser.error("Password must contain 12–128 characters.")

        if password != confirmation:
            parser.error("Passwords do not match.")

        new_hash = PasswordHasher().hash(password)

        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            updated = connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ? AND password_hash = ?
                """,
                (new_hash, user[0], user[1]),
            )

            if updated.rowcount != 1:
                raise RuntimeError(
                    "Account changed during reset. Run the command again."
                )

            revoked = connection.execute(
                "DELETE FROM account_sessions WHERE user_id = ?",
                (user[0],),
            ).rowcount

    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 1
    except (sqlite3.Error, OSError, RuntimeError) as error:
        print(f"Password reset failed: {error}", file=sys.stderr)
        return 1

    print(f"Password reset for {username}.")
    print(f"Revoked {revoked} session(s). Sign in with the new password.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())