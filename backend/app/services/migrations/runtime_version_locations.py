"""Helpers for building Alembic runtime version locations.

This keeps the executed Alembic script tree aligned with capability-owned
`migration_paths` without breaking on revisions that are already mirrored into
the core Alembic directories.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Iterable

from app.services.runtime_assets_installer_core.migrations import extract_revision_id

from .scanner import MigrationScanner

logger = logging.getLogger(__name__)

_RUNTIME_OVERLAY_DIRNAME = ".runtime_capability_migrations"


def _default_version_locations(backend_dir: Path, db_type: str) -> list[Path]:
    common_versions = backend_dir / "alembic_migrations" / "versions"
    locations = [common_versions]

    db_versions = backend_dir / "alembic_migrations" / db_type / "versions"
    if db_versions.exists():
        locations.append(db_versions)

    return [path for path in locations if path.exists()]


def _iter_revision_files(version_dir: Path) -> Iterable[Path]:
    if not version_dir.exists():
        return ()
    return (
        path
        for path in sorted(version_dir.glob("*.py"))
        if not path.name.startswith("__")
    )


def _collect_known_revisions(version_dirs: Iterable[Path]) -> set[str]:
    known: set[str] = set()
    for version_dir in version_dirs:
        for migration_file in _iter_revision_files(version_dir):
            revision = extract_revision_id(migration_file)
            if revision:
                known.add(revision)
    return known


def _materialize_capability_overlay(
    *,
    backend_dir: Path,
    capabilities_root: Path,
    capability_code: str,
    migration_paths: list[str],
    known_revisions: set[str],
) -> Path | None:
    capability_dir = capabilities_root / capability_code
    if not capability_dir.exists():
        return None

    overlay_dir = (
        backend_dir
        / _RUNTIME_OVERLAY_DIRNAME
        / capability_code
    )
    if overlay_dir.exists():
        shutil.rmtree(overlay_dir)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for rel_path in migration_paths:
        versions_dir = capability_dir / rel_path
        if not versions_dir.exists():
            continue
        for migration_file in _iter_revision_files(versions_dir):
            revision = extract_revision_id(migration_file)
            if not revision or revision in known_revisions:
                continue
            shutil.copy2(migration_file, overlay_dir / migration_file.name)
            known_revisions.add(revision)
            copied += 1

    if copied == 0:
        try:
            overlay_dir.rmdir()
        except OSError:
            pass
        return None

    logger.info(
        "Prepared Alembic runtime overlay for %s with %d revision(s)",
        capability_code,
        copied,
    )
    return overlay_dir


def resolve_runtime_version_locations(
    *,
    backend_dir: Path,
    capabilities_root: Path | None,
    db_type: str,
) -> list[str]:
    """Return absolute Alembic version locations for runtime execution."""

    base_locations = _default_version_locations(backend_dir, db_type)
    resolved_locations = [path.resolve() for path in base_locations]

    if capabilities_root is None or not capabilities_root.exists():
        return [path.as_posix() for path in resolved_locations]

    known_revisions = _collect_known_revisions(resolved_locations)
    scanner = MigrationScanner(capabilities_root)
    metadata_list = [
        metadata
        for metadata in scanner.scan_capabilities()
        if metadata.db_type == db_type and metadata.migration_paths
    ]

    for metadata in metadata_list:
        overlay_dir = _materialize_capability_overlay(
            backend_dir=backend_dir,
            capabilities_root=capabilities_root,
            capability_code=metadata.capability_code,
            migration_paths=metadata.migration_paths,
            known_revisions=known_revisions,
        )
        if overlay_dir is not None:
            resolved_locations.append(overlay_dir.resolve())

    deduped: list[str] = []
    seen: set[str] = set()
    for path in resolved_locations:
        normalized = path.as_posix()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def configure_runtime_version_locations(
    *,
    config,
    backend_dir: Path,
    capabilities_root: Path | None,
    db_type: str,
) -> list[str]:
    """Apply runtime version locations to an Alembic config."""

    locations = resolve_runtime_version_locations(
        backend_dir=backend_dir,
        capabilities_root=capabilities_root,
        db_type=db_type,
    )
    if locations:
        config.set_main_option("version_locations", os.pathsep.join(locations))
    return locations
