"""Secure filesystem and command helpers for the cutover runner."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


class CutoverError(RuntimeError):
    """Raised when a cutover gate fails closed."""


def assert_mode(path: Path, expected: int) -> None:
    """Require an exact permission mode and reject symbolic links."""

    if path.is_symlink():
        raise CutoverError(f"Symbolic links are not allowed: {path.name}")
    try:
        actual = path.stat().st_mode & 0o777
    except FileNotFoundError as error:
        raise CutoverError(f"Required secure path is missing: {path.name}") from error
    if actual != expected:
        raise CutoverError(
            f"Invalid permissions for {path.name}: expected {oct(expected)}, got {oct(actual)}"
        )


def assert_private_directory(path: Path) -> None:
    """Require one real 0700 directory."""

    assert_mode(path, 0o700)
    if not path.is_dir():
        raise CutoverError(f"Secure path is not a directory: {path.name}")


def assert_private_file(path: Path, *, max_bytes: int | None = None) -> None:
    """Require one real 0600 regular file with an optional size ceiling."""

    assert_mode(path, 0o600)
    if not path.is_file():
        raise CutoverError(f"Secure path is not a regular file: {path.name}")
    size = path.stat().st_size
    if size <= 0:
        raise CutoverError(f"Secure file is empty: {path.name}")
    if max_bytes is not None and size > max_bytes:
        raise CutoverError(f"Secure file exceeds its size limit: {path.name}")


def write_private_text(path: Path, value: str) -> None:
    """Atomically write operator-only evidence."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write stable JSON evidence with operator-only permissions."""

    write_private_text(
        path,
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    )


class CommandExecutor:
    """Run bounded commands while keeping captured output out of logs."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float = 60.0,
        input_text: str | None = None,
    ) -> str:
        """Return stdout or raise a sanitized failure."""

        try:
            result = subprocess.run(
                list(args),
                check=False,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CutoverError(f"Command unavailable: {Path(args[0]).name}") from error
        if result.returncode != 0:
            raise CutoverError(
                f"Command failed with exit {result.returncode}: {Path(args[0]).name}"
            )
        return result.stdout
