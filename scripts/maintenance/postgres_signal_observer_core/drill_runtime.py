"""Canonical Python runtime contract for the single formal drill facade."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


CANONICAL_LOCAL_CORE_NAME = "mindscape-ai-local-core"
CANONICAL_PYTHON_RELATIVE_PATH = Path(".venv/bin/python")
DRILL_FACADE_RELATIVE_PATH = Path(
    "scripts/maintenance/postgres_signal_observer_drill.py"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FormalExecutorPythonRuntimeContract:
    """Bind one task source tree to the canonical Local Core interpreter."""

    repo_root: Path
    actual_executable: Path = Path(sys.executable)
    runtime_prefix: Path = Path(sys.prefix)

    @property
    def task_repo_root(self) -> Path:
        candidate = Path(self.repo_root)
        if not candidate.is_absolute() or candidate.is_symlink():
            raise ValueError("formal_executor_task_repo_root_invalid")
        return candidate

    @property
    def canonical_repo_root(self) -> Path:
        task_root = self.task_repo_root
        if task_root.name == CANONICAL_LOCAL_CORE_NAME:
            return task_root
        return task_root.parent / CANONICAL_LOCAL_CORE_NAME

    @property
    def python_entry_path(self) -> Path:
        return self.canonical_repo_root / CANONICAL_PYTHON_RELATIVE_PATH

    @property
    def facade_path(self) -> Path:
        return self.task_repo_root / DRILL_FACADE_RELATIVE_PATH

    def validate(self) -> None:
        canonical_root = self.canonical_repo_root
        if (
            not canonical_root.is_absolute()
            or canonical_root.is_symlink()
            or canonical_root.name != CANONICAL_LOCAL_CORE_NAME
            or not canonical_root.is_dir()
            or not (canonical_root / ".git").is_dir()
        ):
            raise ValueError("formal_executor_canonical_repo_identity_mismatch")

        python_entry = self.python_entry_path
        try:
            entry_metadata = python_entry.lstat()
            resolved_python = python_entry.resolve(strict=True)
            target_metadata = resolved_python.stat()
        except OSError as exc:
            raise ValueError("formal_executor_python_runtime_unavailable") from exc
        if not (stat.S_ISREG(entry_metadata.st_mode) or stat.S_ISLNK(entry_metadata.st_mode)):
            raise ValueError("formal_executor_python_entry_type_invalid")
        if not stat.S_ISREG(target_metadata.st_mode) or not os.access(
            python_entry, os.X_OK
        ):
            raise ValueError("formal_executor_python_runtime_not_executable")

        actual = Path(self.actual_executable)
        if not actual.is_absolute() or actual != python_entry:
            raise ValueError("formal_executor_python_runtime_identity_mismatch")
        expected_prefix = canonical_root / ".venv"
        if Path(self.runtime_prefix) != expected_prefix:
            raise ValueError("formal_executor_python_prefix_identity_mismatch")

        facade = self.facade_path
        if facade.is_symlink() or not facade.is_file():
            raise ValueError("formal_executor_drill_facade_identity_mismatch")

    def facade_argv(self, arguments: Sequence[str]) -> tuple[str, ...]:
        """Build the only shell-free facade invocation prefix."""

        self.validate()
        return (
            str(self.python_entry_path),
            str(self.facade_path),
            *(str(value) for value in arguments),
        )

    def redacted_spec(self) -> dict[str, Any]:
        self.validate()
        python_entry = self.python_entry_path
        resolved_python = python_entry.resolve(strict=True)
        facade = self.facade_path
        argv_prefix = (str(python_entry), str(facade))
        return {
            "contract": "canonical_local_core_venv_python_v1",
            "canonical_repo_root": str(self.canonical_repo_root),
            "task_repo_root": str(self.task_repo_root),
            "python_entry_path": str(python_entry),
            "python_resolved_path": str(resolved_python),
            "python_entry_sha256": _sha256(resolved_python),
            "python_entry_executable": True,
            "runtime_prefix": str(self.runtime_prefix),
            "facade_path": str(facade),
            "facade_sha256": _sha256(facade),
            "argv_prefix_sha256": hashlib.sha256(
                "\0".join(argv_prefix).encode("utf-8")
            ).hexdigest(),
            "path_search": False,
            "host_fallback": False,
            "shell": False,
            "second_launcher": False,
        }
