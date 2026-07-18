"""Secure source-owned materialization for isolated drill preconditions."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


MAX_PRECONDITION_BYTES = 65_536


def secure_create_precondition(path: Path, content: bytes) -> None:
    """Create one exclusive 0600 regular file without following symlinks."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError("drill_precondition_nofollow_unavailable")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    descriptor = os.open(path, flags, 0o600)
    try:
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise RuntimeError("drill_precondition_file_contract_invalid")
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise RuntimeError("drill_precondition_write_incomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def secure_precondition_readback(path: Path) -> dict[str, object]:
    """Read one staged precondition through a verified no-follow fd."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError("drill_precondition_nofollow_unavailable")
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError("drill_precondition_file_contract_invalid")
    flags = os.O_RDONLY | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (metadata.st_dev, metadata.st_ino) != (before.st_dev, before.st_ino)
            or metadata.st_size > MAX_PRECONDITION_BYTES
        ):
            raise RuntimeError("drill_precondition_file_contract_invalid")
        chunks: list[bytes] = []
        remaining = MAX_PRECONDITION_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_PRECONDITION_BYTES:
            raise RuntimeError("drill_precondition_file_contract_invalid")
    finally:
        os.close(descriptor)
    return {
        "path": str(path),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "regular_file": True,
        "symlink": False,
        "content_or_value_disclosed": False,
    }
