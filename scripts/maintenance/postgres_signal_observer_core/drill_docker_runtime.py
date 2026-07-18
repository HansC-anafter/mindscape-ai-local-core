"""Canonical Docker CLI runtime contract for the isolated drill facade."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


CANONICAL_DOCKER_CLI_ENTRY_PATH = Path("/usr/local/bin/docker")
CANONICAL_DOCKER_CLI_TARGET_PATH = Path(
    "/Applications/Docker.app/Contents/Resources/bin/docker"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_docker_argv(*arguments: object) -> tuple[str, ...]:
    """Prefix one Docker operation with the source-owned absolute entry."""

    if not arguments or any(not str(value) for value in arguments):
        raise ValueError("formal_executor_docker_arguments_invalid")
    return (
        str(CANONICAL_DOCKER_CLI_ENTRY_PATH),
        *(str(value) for value in arguments),
    )


def validate_canonical_docker_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Reject bare Docker commands and any executable identity drift."""

    exact = tuple(str(value) for value in argv)
    if not exact or exact[0] != str(CANONICAL_DOCKER_CLI_ENTRY_PATH):
        raise ValueError("formal_executor_docker_argv_identity_mismatch")
    if len(exact) < 2 or any(not value for value in exact[1:]):
        raise ValueError("formal_executor_docker_arguments_invalid")
    return exact


@dataclass(frozen=True)
class FormalExecutorDockerRuntimeContract:
    """Bind every isolated-drill Docker operation to one CLI identity."""

    entry_path: Path = CANONICAL_DOCKER_CLI_ENTRY_PATH
    target_path: Path = CANONICAL_DOCKER_CLI_TARGET_PATH

    def validate(self) -> None:
        entry = Path(self.entry_path)
        target = Path(self.target_path)
        if entry != CANONICAL_DOCKER_CLI_ENTRY_PATH or not entry.is_absolute():
            raise ValueError("formal_executor_docker_entry_identity_mismatch")
        if target != CANONICAL_DOCKER_CLI_TARGET_PATH or not target.is_absolute():
            raise ValueError("formal_executor_docker_target_identity_mismatch")
        try:
            entry_metadata = entry.lstat()
            resolved_entry = entry.resolve(strict=True)
            target_metadata = resolved_entry.stat()
        except OSError as exc:
            raise ValueError("formal_executor_docker_runtime_unavailable") from exc
        if not (
            stat.S_ISREG(entry_metadata.st_mode)
            or stat.S_ISLNK(entry_metadata.st_mode)
        ):
            raise ValueError("formal_executor_docker_entry_type_invalid")
        if resolved_entry != target:
            raise ValueError("formal_executor_docker_target_identity_mismatch")
        if not stat.S_ISREG(target_metadata.st_mode):
            raise ValueError("formal_executor_docker_target_type_invalid")
        if not os.access(entry, os.X_OK) or not os.access(target, os.X_OK):
            raise ValueError("formal_executor_docker_runtime_not_executable")

    def argv(self, arguments: Sequence[str]) -> tuple[str, ...]:
        """Build one validated shell-free Docker argv."""

        self.validate()
        return validate_canonical_docker_argv(
            canonical_docker_argv(*(str(value) for value in arguments))
        )

    def redacted_spec(self) -> dict[str, Any]:
        self.validate()
        entry = Path(self.entry_path)
        target = entry.resolve(strict=True)
        argv_prefix = (str(entry),)
        entry_identity = "\0".join(
            (str(entry), str(target), "symlink" if entry.is_symlink() else "regular")
        )
        return {
            "contract": "canonical_local_core_docker_cli_v1",
            "entry_path": str(entry),
            "entry_is_symlink": entry.is_symlink(),
            "entry_regular_or_symlink": True,
            "entry_executable": True,
            "entry_identity_sha256": hashlib.sha256(
                entry_identity.encode("utf-8")
            ).hexdigest(),
            "target_path": str(target),
            "target_regular_file": True,
            "target_executable": True,
            "target_sha256": _sha256(target),
            "argv_prefix_sha256": hashlib.sha256(
                "\0".join(argv_prefix).encode("utf-8")
            ).hexdigest(),
            "path_search": False,
            "host_environment_override": False,
            "fallback": False,
            "shell": False,
            "second_launcher": False,
        }
