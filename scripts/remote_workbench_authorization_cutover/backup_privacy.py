"""Owner-only filesystem gate for Phase06 database backup evidence."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable

from .io import CutoverError


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def resolve_private_output_directory(raw_path: str) -> Path:
    """Require one existing, real, current-user 0700 backup root."""

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise CutoverError("Backup output directory must be absolute")
    absolute = candidate.absolute()
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as error:
        raise CutoverError("Backup output directory is unavailable") from error
    if absolute != resolved or absolute.is_symlink() or not absolute.is_dir():
        raise CutoverError("Backup output directory must be a real directory")
    metadata = absolute.stat()
    if metadata.st_uid != os.getuid():
        raise CutoverError("Backup output directory must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE:
        raise CutoverError("Backup output directory mode must be 0700")
    return absolute


def _require_private_entry(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise CutoverError("Backup evidence must not contain symbolic links")
    if metadata.st_uid != os.getuid():
        raise CutoverError("Backup evidence must be owned by the current user")
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISDIR(metadata.st_mode):
        if mode != PRIVATE_DIRECTORY_MODE:
            raise CutoverError("Backup evidence directory mode must be 0700")
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise CutoverError("Backup evidence must contain only regular files")
    if mode != PRIVATE_FILE_MODE:
        raise CutoverError("Backup evidence file mode must be 0600")


def verify_private_backup_tree(
    backup_dir: Path,
    *,
    required_artifacts: Iterable[str],
) -> None:
    """Reject any non-owner-only, linked, missing, or special backup artifact."""

    if not backup_dir.is_absolute():
        raise CutoverError("Verified backup path must be absolute")
    try:
        resolved = backup_dir.resolve(strict=True)
    except OSError as error:
        raise CutoverError("Verified backup path is unavailable") from error
    if resolved != backup_dir.absolute():
        raise CutoverError("Verified backup path must not traverse symbolic links")
    _require_private_entry(backup_dir)
    for path in backup_dir.rglob("*"):
        _require_private_entry(path)
    for relative in required_artifacts:
        artifact = backup_dir / relative
        try:
            artifact.relative_to(backup_dir)
            _require_private_entry(artifact)
        except (OSError, ValueError) as error:
            raise CutoverError("Required private database artifact is unavailable") from error
