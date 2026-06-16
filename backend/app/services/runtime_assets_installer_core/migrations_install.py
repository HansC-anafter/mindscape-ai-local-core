"""Migration install validation helpers for runtime assets."""

import logging
from pathlib import Path

from ..install_result import InstallResult
from .migrations_metadata import (
    _get_alembic_versions_dir,
    detect_revision_conflicts,
    extract_branch_labels,
    extract_down_revision,
)

logger = logging.getLogger(f"{__package__}.migrations")


def install_migrations(
    cap_dir: Path,
    capability_code: str,
    local_core_root: Path,
    result: InstallResult,
) -> None:
    """Validate capability migration files without mirroring them into core Alembic trees."""
    migrations_yaml = cap_dir / "migrations.yaml"
    migrations_dir = cap_dir / "migrations"

    if migrations_yaml.exists() and not migrations_dir.exists():
        migrations_versions_dir = cap_dir / "migrations" / "versions"
        if migrations_versions_dir.exists():
            migrations_dir = migrations_versions_dir.parent
            logger.debug(
                f"Found migrations in migrations/versions/ subdirectory for {capability_code}"
            )
        else:
            logger.warning(
                f"Capability {capability_code} has migrations.yaml but missing migrations/ directory. "
                "Creating migrations/ directory automatically."
            )
            migrations_dir.mkdir(parents=True, exist_ok=True)
            init_file = migrations_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Migration files directory\n")

    if not migrations_dir.exists():
        return

    alembic_versions_dir = _get_alembic_versions_dir(local_core_root)
    if not alembic_versions_dir.exists():
        error_message = f"Alembic versions directory not found: {alembic_versions_dir}"
        logger.error(error_message)
        result.add_error(error_message)
        return

    all_py_files = list(migrations_dir.rglob("*.py"))
    migration_files = [file for file in all_py_files if not file.name.startswith("__")]

    logger.debug(
        f"Migration check for {capability_code}: "
        f"all_py_files={[file.name for file in all_py_files]}, "
        f"migration_files={[file.name for file in migration_files]}, "
        f"migrations_yaml.exists()={migrations_yaml.exists()}"
    )

    if not migration_files:
        if migrations_yaml.exists():
            error_message = (
                f"Capability {capability_code} has migrations.yaml and migrations/ directory, "
                "but no migration files found. Migration files must be included in migrations/ directory."
            )
            logger.error(error_message)
            result.add_error(error_message)
            return
        return

    conflicting_revisions = detect_revision_conflicts(
        capability_code, alembic_versions_dir, migration_files
    )
    if conflicting_revisions:
        error_message = (
            f"Migration revision ID conflict detected for {capability_code}:\n"
        )
        for conflict in conflicting_revisions:
            error_message += (
                f"  Revision {conflict['revision']} is already used by other capabilities: "
                f"{', '.join(conflict['existing_files'])}\n"
            )
        error_message += (
            "Please use a unique revision ID for this capability's migrations."
        )
        logger.error(error_message)
        result.add_error(error_message)
        if result.migration_status is None:
            result.migration_status = {}
        result.migration_status[capability_code] = "conflict"
        return

    registered_files = []
    for migration_file in migration_files:
        logger.debug(f"Registered capability migration: {migration_file.name}")
        registered_files.append(migration_file.name)

        branch = extract_branch_labels(migration_file)
        down_revision = extract_down_revision(migration_file)
        if not branch and down_revision is None:
            result.add_warning(
                f"Migration {migration_file.name} has no branch_labels. "
                f"Set branch_labels = ('{capability_code}',) for Hybrid migration support."
            )

    if registered_files:
        result.extend_installed("migrations", registered_files)
        logger.info(
            "Registered %s capability migration files for %s (execution uses capability-local migration paths)",
            len(registered_files),
            capability_code,
        )
