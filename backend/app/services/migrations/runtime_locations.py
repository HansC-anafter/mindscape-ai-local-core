"""Helpers for wiring runtime capability migration paths into Alembic config."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from alembic.config import Config

from .scanner import MigrationScanner


_REVISION_PATTERN = re.compile(r"""revision\s*=\s*['"]([^'"]+)['"]""")


def _resolve_declared_version_locations(config: Config) -> list[str]:
    version_locations = config.get_main_option("version_locations")
    if not version_locations:
        return []

    config_dir = (
        Path(config.config_file_name).resolve().parent
        if config.config_file_name
        else Path.cwd()
    )
    resolved_locations: list[str] = []
    for location in version_locations.split(os.pathsep):
        location = location.strip()
        if not location:
            continue
        location_path = Path(location)
        if not location_path.is_absolute():
            location_path = (config_dir / location_path).resolve()
        else:
            location_path = location_path.resolve()
        resolved_locations.append(location_path.as_posix())
    return resolved_locations


def _iter_revision_files(location: Path) -> list[Path]:
    if not location.exists() or not location.is_dir():
        return []

    return sorted(
        path
        for path in location.glob("*.py")
        if path.name != "__init__.py"
    )


def _read_revision_id(path: Path) -> str | None:
    try:
        match = _REVISION_PATTERN.search(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        match = _REVISION_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore"))
    if match is None:
        return None
    return match.group(1)


def _collect_known_revision_ids(locations: Iterable[str]) -> set[str]:
    revision_ids: set[str] = set()
    for location in locations:
        for revision_file in _iter_revision_files(Path(location)):
            revision_id = _read_revision_id(revision_file)
            if revision_id:
                revision_ids.add(revision_id)
    return revision_ids


def _stage_runtime_revision_subset(
    *,
    db_type: str,
    capability_code: str,
    source_dir: Path,
    revision_files: list[Path],
) -> str:
    digest = hashlib.sha1(
        "\n".join(
            [
                source_dir.as_posix(),
                *(path.name for path in revision_files),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    staging_root = Path(tempfile.gettempdir()) / "mindscape_runtime_migrations" / db_type
    staged_dir = staging_root / f"{capability_code}_{digest}"
    staged_dir.mkdir(parents=True, exist_ok=True)

    for revision_file in revision_files:
        shutil.copy2(revision_file, staged_dir / revision_file.name)

    return staged_dir.as_posix()


def _resolve_capability_version_locations(
    *,
    capabilities_root: Path,
    db_type: str,
    known_revision_ids: set[str],
) -> list[str]:
    resolved_locations: list[str] = []
    scanner = MigrationScanner(capabilities_root)
    for metadata in sorted(
        scanner.scan_capabilities(),
        key=lambda item: item.capability_code,
    ):
        if metadata.db_type != db_type:
            continue
        for rel_path in metadata.migration_paths:
            candidate = (capabilities_root / metadata.capability_code / rel_path).resolve()
            if not candidate.exists() or not candidate.is_dir():
                continue

            revision_files = _iter_revision_files(candidate)
            if not revision_files:
                continue

            unique_revision_files: list[Path] = []
            duplicate_detected = False
            for revision_file in revision_files:
                revision_id = _read_revision_id(revision_file)
                if not revision_id:
                    unique_revision_files.append(revision_file)
                    continue
                if revision_id in known_revision_ids:
                    duplicate_detected = True
                    continue
                unique_revision_files.append(revision_file)
                known_revision_ids.add(revision_id)

            if not unique_revision_files:
                continue

            if duplicate_detected:
                resolved_locations.append(
                    _stage_runtime_revision_subset(
                        db_type=db_type,
                        capability_code=metadata.capability_code,
                        source_dir=candidate,
                        revision_files=unique_revision_files,
                    )
                )
            else:
                resolved_locations.append(candidate.as_posix())
    return resolved_locations


def configure_runtime_version_locations(
    config: Config,
    *,
    capabilities_root: Path,
    db_type: str,
) -> list[str]:
    """Merge declared Alembic version paths with runtime capability migration paths."""
    declared_locations = _resolve_declared_version_locations(config)
    known_revision_ids = _collect_known_revision_ids(declared_locations)
    merged_locations: list[str] = []
    for location in [
        *declared_locations,
        *_resolve_capability_version_locations(
            capabilities_root=capabilities_root,
            db_type=db_type,
            known_revision_ids=known_revision_ids,
        ),
    ]:
        if location not in merged_locations:
            merged_locations.append(location)

    if merged_locations:
        config.set_main_option("version_locations", os.pathsep.join(merged_locations))
    return merged_locations
