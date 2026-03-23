"""
Migration installation and execution helpers for runtime assets.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import yaml

from ..install_result import InstallResult

logger = logging.getLogger(__name__)


def _get_alembic_versions_dir(local_core_root: Path) -> Path:
    """Return the Alembic versions directory used by Local-Core."""
    return (
        local_core_root
        / "backend"
        / "alembic_migrations"
        / "postgres"
        / "versions"
    )


def install_migrations(
    cap_dir: Path,
    capability_code: str,
    local_core_root: Path,
    result: InstallResult,
) -> None:
    """Install capability migration files into the Alembic versions directory."""
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

    installed_files = []
    for migration_file in migration_files:
        target_file = alembic_versions_dir / migration_file.name
        shutil.copy2(migration_file, target_file)
        logger.debug(f"Installed migration: {migration_file.name}")
        installed_files.append(migration_file.name)

        branch = extract_branch_labels(migration_file)
        down_revision = extract_down_revision(migration_file)
        if not branch and down_revision is None:
            result.add_warning(
                f"Migration {migration_file.name} has no branch_labels. "
                f"Set branch_labels = ('{capability_code}',) for Hybrid migration support."
            )

    if installed_files:
        result.extend_installed("migrations", installed_files)
        logger.info(
            f"Installed {len(installed_files)} migration files for {capability_code}"
        )


def extract_branch_labels(migration_file: Path) -> tuple:
    """Extract Alembic branch_labels from a migration file."""
    import re

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
    import re

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
    import re

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


def execute_migrations(
    local_core_root: Path,
    capabilities_dir: Path,
    capability_code: str,
    result: InstallResult,
) -> None:
    """Execute installed migrations for a specific capability."""
    alembic_config = local_core_root / "backend" / "alembic.ini"
    if not alembic_config.exists():
        logger.warning(
            f"Alembic config not found: {alembic_config}, skipping migration execution"
        )
        result.add_warning(
            "Migrations installed but not executed (alembic config not found)"
        )
        return

    engine = None
    try:
        logger.info(f"Executing database migrations for {capability_code}...")

        capability_dir = capabilities_dir / capability_code
        migrations_yaml = capability_dir / "migrations.yaml"
        revisions = []
        use_branch_scoped = False
        alembic_versions_dir = _get_alembic_versions_dir(local_core_root)

        if migrations_yaml.exists():
            with open(migrations_yaml, "r") as file:
                migration_data = yaml.safe_load(file)
            revisions = migration_data.get("revisions", [])

            migration_paths = migration_data.get("migration_paths", ["migrations/versions/"])
            actual_revisions = set()
            for migration_path in migration_paths:
                versions_dir = capability_dir / migration_path
                if not versions_dir.exists():
                    continue
                for migration_file in versions_dir.glob("*.py"):
                    if migration_file.name.startswith("__"):
                        continue
                    revision_id = extract_revision_id(migration_file)
                    if revision_id:
                        actual_revisions.add(revision_id)

            declared_set = set(str(revision) for revision in revisions)
            undeclared = actual_revisions - declared_set
            if undeclared:
                drift_message = (
                    f"Migration drift detected for {capability_code}: "
                    f"files exist for revisions {sorted(undeclared)} "
                    "but they are NOT declared in migrations.yaml. "
                    "These migrations will NOT be executed until added to the revisions list."
                )
                logger.warning(drift_message)
                result.add_warning(drift_message)
        else:
            if pack_has_branch_label(capability_code, alembic_versions_dir):
                logger.info(
                    f"No migrations.yaml for {capability_code}, but branch_labels found — will use branch-scoped auto-discover"
                )
                revisions = []
                use_branch_scoped = True
            else:
                logger.warning(
                    f"No migrations.yaml and no branch_labels for {capability_code}, skipping migration execution (set branch_labels to enable auto-discover)"
                )
                result.add_warning(
                    f"Migrations installed but not executed for {capability_code}: "
                    "no migrations.yaml and no branch_labels. "
                    f"Add branch_labels = ('{capability_code}',) to enable auto-discover."
                )
                return

        if not revisions and not use_branch_scoped:
            logger.info(f"No migrations found for {capability_code}")
            return

        if alembic_versions_dir.exists():
            existing_revisions = {}
            capability_patterns = [
                capability_code.replace("_", " "),
                capability_code.replace("_", ""),
                capability_code,
            ]

            for migration_file in alembic_versions_dir.glob("*.py"):
                if migration_file.name.startswith("__"):
                    continue
                try:
                    revision = extract_revision_id(migration_file)
                    if not revision:
                        continue

                    file_content = migration_file.read_text().lower()
                    is_current_capability = any(
                        pattern in file_content for pattern in capability_patterns
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
            for revision in revisions:
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

        from app.services.migrations.orchestrator import MigrationOrchestrator
        from sqlalchemy import create_engine, inspect, text
        from app.database.config import get_postgres_url_core

        capabilities_root = local_core_root / "backend" / "app" / "capabilities"
        alembic_configs = {"postgres": alembic_config}
        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

        engine = create_engine(get_postgres_url_core())
        revision_expected_tables = {}
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        for revision in revisions:
            migration_files = list(
                (local_core_root / "backend" / "alembic" / "postgres" / "versions").glob(
                    f"{revision}_*.py"
                )
            )
            expected_tables = []
            for migration_file in migration_files:
                try:
                    content = migration_file.read_text()
                    import re

                    table_matches = re.findall(
                        r"op\.create_table\(['\"]([^'\"]+)['\"]", content
                    )
                    expected_tables.extend(
                        [table for table in table_matches if capability_code in table]
                    )
                except Exception:
                    pass
            revision_expected_tables[revision] = expected_tables

        with engine.connect() as connection:
            result_query = connection.execute(text("SELECT version_num FROM alembic_version"))
            applied_revisions = {row[0] for row in result_query}

            for revision in revisions:
                if revision not in applied_revisions:
                    continue
                expected_tables = revision_expected_tables.get(revision, [])
                if not expected_tables:
                    continue
                missing_tables = [
                    table for table in expected_tables if table not in existing_tables
                ]
                if not missing_tables:
                    continue
                logger.warning(
                    f"Revision {revision} is marked as applied but tables are missing: {missing_tables}"
                )
                logger.info(
                    f"Removing revision {revision} from alembic_version to allow re-execution"
                )
                connection.execute(
                    text(
                        f"DELETE FROM alembic_version WHERE version_num = '{revision}'"
                    )
                )
                connection.commit()
                logger.info(
                    f"Removed revision {revision}, will re-execute migration"
                )

        if pack_has_branch_label(capability_code, alembic_versions_dir):
            target = f"{capability_code}@head"
            logger.info(
                f"Branch-scoped migration: upgrading {target} for {capability_code}"
            )
            try:
                upgrade_result = orchestrator._run_alembic_upgrade(alembic_config, target)
            except Exception as exc:
                logger.warning(
                    f"Branch {target} upgrade failed ({exc}), falling back to per-revision"
                )
                upgrade_result = False

            if upgrade_result:
                logger.info(f"Branch-scoped migration completed for {capability_code}")
            elif revisions:
                logger.info(f"Falling back to per-revision for {capability_code}")
                for revision in revisions:
                    logger.info(
                        f"Executing migration {revision} for {capability_code}..."
                    )
                    revision_result = orchestrator._run_alembic_upgrade(
                        alembic_config, revision
                    )
                    if revision_result:
                        continue
                    error_message = (
                        f"Migration {revision} failed for {capability_code}"
                    )
                    logger.error(error_message)
                    result.add_warning(error_message)
                    if result.migration_status is None:
                        result.migration_status = {}
                    result.migration_status[capability_code] = "failed"
                    return
            else:
                error_message = (
                    f"Branch-scoped migration failed for {capability_code} "
                    "and no revisions list to fall back to"
                )
                logger.error(error_message)
                result.add_warning(error_message)
                if result.migration_status is None:
                    result.migration_status = {}
                result.migration_status[capability_code] = "failed"
                return
        else:
            for revision in revisions:
                logger.info(f"Executing migration {revision} for {capability_code}...")
                upgrade_result = orchestrator._run_alembic_upgrade(
                    alembic_config, revision
                )
                if upgrade_result:
                    continue
                error_message = f"Migration {revision} failed for {capability_code}"
                logger.error(error_message)
                result.add_warning(error_message)
                if result.migration_status is None:
                    result.migration_status = {}
                result.migration_status[capability_code] = "failed"
                return

        inspector = inspect(engine)
        existing_tables_after = set(inspector.get_table_names())
        for revision in revisions:
            expected_tables = revision_expected_tables.get(revision, [])
            if not expected_tables:
                continue
            still_missing = [
                table for table in expected_tables if table not in existing_tables_after
            ]
            if not still_missing:
                continue
            error_message = (
                f"Migration {revision} completed but tables still missing: {still_missing}"
            )
            logger.error(error_message)
            result.add_warning(error_message)
            if result.migration_status is None:
                result.migration_status = {}
            result.migration_status[capability_code] = "failed"
            return

        logger.info(f"Successfully executed migrations for {capability_code}")
        if result.migration_status is None:
            result.migration_status = {}
        result.migration_status[capability_code] = "applied"
    except Exception as exc:
        error_message = f"Migration execution error: {exc}"
        logger.error(error_message, exc_info=True)
        result.add_warning(error_message)
        if result.migration_status is None:
            result.migration_status = {}
        result.migration_status[capability_code] = "error"
    finally:
        try:
            engine.dispose()
        except Exception:
            pass
