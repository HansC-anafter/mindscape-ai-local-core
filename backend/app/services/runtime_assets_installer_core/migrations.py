"""Migration execution facade for runtime assets."""

import logging
from pathlib import Path

import yaml

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    check_core_write_readiness,
)
from ..install_result import InstallResult
from .migrations_install import install_migrations
from .migrations_metadata import (
    _collect_migration_files,
    _get_alembic_versions_dir,
    detect_revision_conflicts,
    extract_branch_labels,
    extract_down_revision,
    extract_revision_id,
    pack_declares_branch_label,
    pack_has_branch_label,
)

logger = logging.getLogger(__name__)


def _resolve_applied_revisions(
    orchestrator,
    current_revisions: set[str],
) -> set[str]:
    try:
        return {
            str(revision)
            for revision in orchestrator._get_applied_revisions(
                "postgres",
                current_revisions,
            )
        }
    except Exception as exc:
        logger.warning(
            "Could not resolve applied migration ancestry; falling back to current heads: %s",
            exc,
        )
        return {str(revision) for revision in current_revisions}


def _pending_revisions(
    revisions: list[str],
    applied_revisions: set[str],
) -> list[str]:
    applied = {str(revision) for revision in applied_revisions}
    return [str(revision) for revision in revisions if str(revision) not in applied]


def _should_use_branch_scoped_upgrade(
    revisions: list[str],
    branch_auto_discover: bool,
) -> bool:
    """Return whether migration execution must target a capability branch head."""
    return branch_auto_discover and not revisions


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
        migration_data = {}
        revisions = []
        use_branch_scoped = False
        alembic_versions_dir = _get_alembic_versions_dir(local_core_root)
        migration_paths = ["migrations/versions/"]
        current_migration_files: list[Path] = []

        if migrations_yaml.exists():
            with open(migrations_yaml, "r") as file:
                migration_data = yaml.safe_load(file)
            revisions = migration_data.get("revisions", [])
            migration_paths = migration_data.get("migration_paths", migration_paths)
            current_migration_files = _collect_migration_files(
                capability_dir,
                migration_paths,
            )
            actual_revisions = set()
            for migration_file in current_migration_files:
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
            current_migration_files = _collect_migration_files(
                capability_dir,
                migration_paths,
            )
            if pack_declares_branch_label(capability_code, current_migration_files):
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

        if not current_migration_files:
            current_migration_files = _collect_migration_files(
                capability_dir,
                migration_paths,
            )

        conflicting_revisions = detect_revision_conflicts(
            capability_code,
            alembic_versions_dir,
            current_migration_files,
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
        from sqlalchemy import inspect, text
        from app.database.config import get_postgres_url_core_session
        from app.database.engine_factory import create_session_semantics_engine

        readiness = check_core_write_readiness(
            operation=f"capability_migration:{capability_code}"
        )
        if not readiness.ready:
            if result.migration_status is None:
                result.migration_status = {}
            result.migration_status[capability_code] = "waiting_db"
            raise DatabaseWriteNotReadyError(readiness)

        capabilities_root = local_core_root / "backend" / "app" / "capabilities"
        alembic_configs = {"postgres": alembic_config}
        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

        engine = create_session_semantics_engine(
            get_postgres_url_core_session(),
            "local-core-runtime-assets-migration-check",
        )
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
            current_revisions = {str(row[0]) for row in result_query}
            applied_revisions = _resolve_applied_revisions(
                orchestrator,
                current_revisions,
            )

            for revision in revisions:
                if revision not in current_revisions:
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
                applied_revisions.discard(str(revision))
                logger.info(
                    f"Removed revision {revision}, will re-execute migration"
                )

        pending_revisions = _pending_revisions(revisions, applied_revisions)

        if _should_use_branch_scoped_upgrade(revisions, use_branch_scoped):
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
                if not pending_revisions:
                    logger.info(
                        f"No pending per-revision migrations for {capability_code}; "
                        "all declared revisions are already in the applied ancestry"
                    )
                    result.add_warning(
                        f"Branch-scoped migration failed for {capability_code}, "
                        "but declared revisions are already applied"
                    )
                    if result.migration_status is None:
                        result.migration_status = {}
                    result.migration_status[capability_code] = "applied"
                    return
                logger.info(f"Falling back to per-revision for {capability_code}")
                for revision in pending_revisions:
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
            if not pending_revisions:
                logger.info(
                    f"No pending migrations for {capability_code}; declared revisions are already applied"
                )
            for revision in pending_revisions:
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
    except DatabaseWriteNotReadyError:
        raise
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
