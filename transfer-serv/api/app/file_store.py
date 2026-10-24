import os
import re
import stat

from .storage import UPLOAD_PATH


def path_parts(value: str) -> list[str]:
    parts = value.split("/")

    if (
        not value
        or len(value.encode("utf-8")) > 1024
        or chr(92) in value
        or any(part in ("", ".", "..") for part in parts)
        or any(len(part.encode("utf-8")) > 255 for part in parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise ValueError("Invalid storage path.")

    return parts


def open_stored_file(
    transfer_id: str,
    relative_path: str,
    *,
    write: bool = False,
    create: bool = False,
):
    if re.fullmatch(r"[A-Za-z0-9_-]{32}", transfer_id) is None:
        raise ValueError("Invalid transfer ID.")

    parts = [transfer_id, *path_parts(relative_path)]

    if write and create:
        UPLOAD_PATH.mkdir(parents=True, exist_ok=True)

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = os.open(UPLOAD_PATH.resolve(), directory_flags)

    try:
        for part in parts[:-1]:
            if write and create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass

            child = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = child

        flags = os.O_RDWR if write else os.O_RDONLY
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK

        if write and create:
            flags |= os.O_CREAT

        descriptor = os.open(
            parts[-1],
            flags,
            mode=0o600,
            dir_fd=current,
        )

        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("Storage entry is not a regular file.")

            return os.fdopen(descriptor, "r+b" if write else "rb")
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(current)