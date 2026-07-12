"""Host-global process lock for the single Phase06 runner."""

from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .io import CutoverError, assert_private_directory


LOCK_FILE_NAME = "authorization-cutover.lock"
DEFAULT_STATE_DIRECTORY = "~/.mindscape/remote-workbench-bridge"


def _state_directory() -> Path:
    raw = os.getenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", DEFAULT_STATE_DIRECTORY)
    expanded = Path(raw).expanduser()
    if not expanded.is_absolute():
        raise CutoverError("Bridge state directory must be absolute")
    absolute = expanded.absolute()
    if absolute.is_symlink() or absolute.resolve(strict=False) != absolute:
        raise CutoverError("Bridge state directory must not traverse symbolic links")
    if not absolute.exists():
        absolute.mkdir(mode=0o700, parents=True)
    assert_private_directory(absolute)
    if absolute.stat().st_uid != os.getuid():
        raise CutoverError("Bridge state directory must be owned by the current operator")
    return absolute


@contextmanager
def phase06_runner_lock() -> Iterator[Path]:
    """Hold one non-blocking host lock across repository preflight and workflow."""

    state_directory = _state_directory()
    path = state_directory / LOCK_FILE_NAME
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise CutoverError("Phase06 runner lock file is unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise CutoverError("Phase06 runner lock file is not operator-private")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CutoverError("Another Phase06 runner already owns the host lock") from error
        yield path
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)
