"""Opaque, versioned E2EE metadata. No secret keys enter this module."""
import base64
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EncryptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=2, le=2)
    manifest: str = Field(strict=True, min_length=40, max_length=524288)

    @field_validator("manifest")
    @classmethod
    def valid_manifest(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid encrypted manifest.")
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if len(raw) < 29 or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError("Invalid encrypted manifest.")
        return value


def encryption_record(connection, transfer_id):
    row = connection.execute(
        "SELECT version, manifest FROM transfer_encryption WHERE transfer_id = ?",
        (transfer_id,),
    ).fetchone()
    return {"version": row[0], "manifest": row[1]} if row else None
