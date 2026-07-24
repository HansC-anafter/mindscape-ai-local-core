"""Migration metadata parsing and conflict detection helpers."""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(f"{__package__}.migrations")


_PACK_OWNER_CAPABILITY_PATTERN = re.compile(
    r"""\bpack_owner_capability\b\s*(?::\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]"""
)


def _get_alembic_versions_dir(local_core_root: Path) -> Path:
    """Return the Alembic versions directory used by Local-Core."""
    return (
        local_core_root
        / "backend"
        / "alembic_migrations"
        / "postgres"
        / "versions"
    )


def _collect_migration_files(
    capability_dir: Path,
    migration_paths: list[str] | None = None,
) -> list[Path]:
    collected: list[Path] = []
    for migration_path in migration_paths or ["migrations/versions/"]:
        versions_dir = capability_dir / migration_path
        if not versions_dir.exists():
            continue
        for migration_file in versions_dir.glob("*.py"):
            if migration_file.name.startswith("__"):
                continue
            collected.append(migration_file)
    return collected


def extract_branch_labels(migration_file: Path) -> tuple:
    """Extract Alembic branch_labels from a migration file."""
    try:
        content = migration_file.read_text()
        match = re.search(
            r"""branch_labels\s*(?::\s*[^=]+)?\s*=\s*\(([^)]*)\)""",
            content,
        )
        if match:
            inner = match.group(1).strip()
            if inner:
                labels = re.findall(r"""['"]([^'"]+)['"]""", inner)
                return tuple(labels)
        if re.search(r"""branch_labels\s*(?::\s*[^=]+)?\s*=\s*None""", content):
            return ()
    except Exception:
        pass
    return ()


def extract_revision_id(migration_file: Path) -> Optional[str]:
    """Extract the authoritative Alembic revision id from a migration file."""
    try:
        content = migration_file.read_text()
        match = re.search(
            r"""\brevision\b\s*(?::\s*[^=]+)?\s*=\s*['"]([^'"]+)['"]""",
            content,
        )
        if match:
            return match.group(1).strip() or None
    except Exception:
        pass

    stem = migration_file.stem.strip()
    return stem or None


def extract_down_revision(migration_file: Path) -> Optional[str]:
    """Extract the Alembic down_revision from a migration file."""
    try:
        content = migration_file.read_text()
        if re.search(
            r"""\bdown_revision\b\s*(?::\s*[^=]+)?\s*=\s*None""",
            content,
        ):
            return None

        match = re.search(
            r"""\bdown_revision\b\s*(?::\s*[^=]+)?\s*=\s*['"]([^'"]+)['"]""",
            content,
        )
        if match:
            return match.group(1).strip() or None
    except Exception:
        pass

    return None


def extract_pack_owner_capability(migration_file: Path) -> Optional[str]:
    """Return the exact pack owner declared by a core graph-anchor tombstone."""
    if not migration_file.name.endswith("_pack_schema_tombstone.py"):
        return None
    try:
        match = _PACK_OWNER_CAPABILITY_PATTERN.search(
            migration_file.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError):
        return None
    if match is None:
        return None
    return match.group(1).strip() or None


def detect_revision_conflicts(
    capability_code: str,
    alembic_versions_dir: Path,
    incoming_migration_files: list[Path],
) -> list[dict]:
    """Detect revision collisions with installed migrations.

    Incoming filenames are treated as belonging to the current capability so
    reinstalling the same pack does not self-conflict after files are copied.
    """
    if not alembic_versions_dir.exists():
        return []

    incoming_filenames = {
        migration_file.name for migration_file in incoming_migration_files
    }
    incoming_revisions = {
        revision_id
        for migration_file in incoming_migration_files
        if (revision_id := extract_revision_id(migration_file))
    }

    existing_revisions: dict[str, list[dict]] = {}
    for migration_file in alembic_versions_dir.glob("*.py"):
        if migration_file.name.startswith("__"):
            continue
        try:
            revision = extract_revision_id(migration_file)
            if not revision or revision not in incoming_revisions:
                continue

            is_current_capability = migration_file.name in incoming_filenames
            if not is_current_capability:
                is_current_capability = capability_code in extract_branch_labels(
                    migration_file
                )
            if not is_current_capability:
                is_current_capability = (
                    extract_pack_owner_capability(migration_file) == capability_code
                )

            existing_revisions.setdefault(revision, []).append(
                {
                    "file": migration_file.name,
                    "is_current_capability": is_current_capability,
                }
            )
        except Exception:
            continue

    conflicting_revisions = []
    for revision in sorted(incoming_revisions):
        if revision not in existing_revisions:
            continue
        other_capability_files = [
            file_info
            for file_info in existing_revisions[revision]
            if not file_info["is_current_capability"]
        ]
        if other_capability_files:
            conflicting_revisions.append(
                {
                    "revision": revision,
                    "existing_files": [
                        file_info["file"] for file_info in other_capability_files
                    ],
                }
            )

    return conflicting_revisions


def pack_has_branch_label(capability_code: str, alembic_versions_dir: Path) -> bool:
    """Check whether any installed migration file declares the capability branch."""
    if not alembic_versions_dir.exists():
        return False
    for migration_file in alembic_versions_dir.glob("*.py"):
        if migration_file.name.startswith("__"):
            continue
        labels = extract_branch_labels(migration_file)
        if capability_code in labels:
            return True
    return False


def pack_declares_branch_label(
    capability_code: str,
    migration_files: list[Path],
) -> bool:
    """Check whether capability-local migration files declare the capability branch."""
    for migration_file in migration_files:
        labels = extract_branch_labels(migration_file)
        if capability_code in labels:
            return True
    return False
