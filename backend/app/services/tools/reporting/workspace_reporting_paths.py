"""Workspace reporting path validation helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Optional


_SAFE_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_relative_to(child: Path, parent: Path) -> bool:
    """Return whether a resolved child path is within a resolved parent path."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def contains_symlink(path: Path, sandbox_root: Path) -> bool:
    """Return whether an existing component under the sandbox is a symlink."""
    lexical = Path(os.path.abspath(path))
    if not is_relative_to(lexical, sandbox_root):
        return False
    current = sandbox_root
    for part in lexical.relative_to(sandbox_root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def validate_relative_path(
    value: Optional[str],
    *,
    field_name: str,
    default: Optional[str] = None,
) -> PurePosixPath:
    """Validate a portable relative path without traversal segments."""
    normalized = (value or default or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if normalized.startswith("/"):
        raise ValueError(f"{field_name} must be a safe relative path")
    normalized = normalized.rstrip("/")
    if "\\" in normalized:
        raise ValueError(f"{field_name} must use forward slashes")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{field_name} must be a safe relative path")
    return path


def validate_workspace_id(workspace_id: Optional[str]) -> Optional[str]:
    """Validate an optional workspace identifier."""
    if workspace_id is None:
        return None
    value = workspace_id.strip()
    if not value or not _SAFE_WORKSPACE_ID_RE.match(value):
        raise ValueError("workspace_id contains unsupported characters")
    return value


def resolve_workspace_sandbox(
    *,
    workspace_id: Optional[str],
    sandbox_path: Optional[str],
) -> tuple[Optional[str], Path]:
    """Resolve and authorize a workspace sandbox under DATA_DIR/workspaces."""
    safe_workspace_id = validate_workspace_id(workspace_id)
    data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
    workspaces_root = (data_dir / "workspaces").resolve()

    if sandbox_path:
        sandbox_root = Path(sandbox_path).expanduser().resolve()
    elif safe_workspace_id:
        sandbox_root = (workspaces_root / safe_workspace_id / "sandbox").resolve()
    else:
        raise ValueError("workspace_id or sandbox_path is required")

    if not is_relative_to(sandbox_root, workspaces_root):
        raise ValueError("sandbox_path must be under DATA_DIR/workspaces")
    if safe_workspace_id:
        workspace_root = (workspaces_root / safe_workspace_id).resolve()
        if not is_relative_to(sandbox_root, workspace_root):
            raise ValueError("sandbox_path must belong to workspace_id")

    return safe_workspace_id, sandbox_root


def resolve_sandbox_relative_path(
    sandbox_root: Path,
    relative_path: PurePosixPath,
    *,
    field_name: str,
) -> Path:
    """Resolve a validated relative path and keep it within the sandbox."""
    target = sandbox_root.joinpath(*relative_path.parts).resolve()
    if not is_relative_to(target, sandbox_root):
        raise ValueError(f"{field_name} must remain under sandbox root")
    return target


__all__ = [
    "contains_symlink",
    "is_relative_to",
    "resolve_sandbox_relative_path",
    "resolve_workspace_sandbox",
    "validate_relative_path",
    "validate_workspace_id",
]
