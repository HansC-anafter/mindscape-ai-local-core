"""Shared path helpers for pack-owned contracts and runtime alias roots."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def resolve_runtime_contracts_root(local_core_root: Path) -> Path:
    """Return the generated runtime-contract root under local-core data/."""
    return Path(local_core_root) / "data" / "runtime_contracts"


def resolve_capability_import_roots(capabilities_dir: Path) -> list[Path]:
    """Return import roots for installed capability packs."""
    capabilities_dir = Path(capabilities_dir)
    app_root = capabilities_dir.parent
    backend_root = app_root.parent
    return [backend_root, app_root, capabilities_dir]


def resolve_capability_runtime_import_roots(capability_dir: Path) -> list[Path]:
    """Return runtime import roots for a specific installed capability."""
    capability_dir = Path(capability_dir)
    capabilities_dir = capability_dir.parent
    backend_root, app_root, capabilities_root = resolve_capability_import_roots(
        capabilities_dir
    )
    local_core_root = backend_root.parent
    return [
        backend_root,
        app_root,
        capabilities_root,
        resolve_runtime_contracts_root(local_core_root),
    ]


def prepend_import_paths(sys_path: list[str], paths: Iterable[Path]) -> None:
    """Insert paths at the front of sys.path while preserving order and uniqueness."""
    normalized_paths = [str(Path(path)) for path in paths]
    for path_str in reversed(normalized_paths):
        if path_str in sys_path:
            sys_path.remove(path_str)
        sys_path.insert(0, path_str)


def build_validation_pythonpath(local_core_root: Path, capabilities_dir: Path) -> str:
    """Build the subprocess PYTHONPATH used by install-time validators."""
    local_core_root = Path(local_core_root)
    parts = [
        local_core_root,
        *resolve_capability_import_roots(capabilities_dir),
        resolve_runtime_contracts_root(local_core_root),
    ]
    ordered_unique: list[str] = []
    for part in parts:
        part_str = str(part)
        if part_str not in ordered_unique:
            ordered_unique.append(part_str)
    return ":".join(ordered_unique)
