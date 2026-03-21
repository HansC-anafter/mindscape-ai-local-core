"""Migration orchestrator for coordinating multi-capability migrations."""

import logging
import subprocess
import os
import sys
from typing import List, Dict
from pathlib import Path
from enum import Enum

from alembic.config import Config
from alembic.script import ScriptDirectory

from .scanner import MigrationScanner, MigrationMetadata
from .dependency_resolver import DependencyResolver
from .validator import MigrationValidator

logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class MigrationOrchestrator:
    """Orchestrates migrations across multiple capabilities and databases."""

    def __init__(self, capabilities_root: Path, alembic_configs: Dict[str, Path]):
        """
        Args:
            capabilities_root: Root directory containing capabilities
            alembic_configs: Dict mapping db_type to alembic.ini path
        """
        self.capabilities_root = capabilities_root
        self.alembic_configs = alembic_configs
        self.scanner = MigrationScanner(capabilities_root)
        self.dependency_resolver = DependencyResolver()
        self.validator = MigrationValidator()

    def dry_run(self, db_type: str) -> Dict:
        """Perform a dry-run to show what migrations would be executed."""
        logger.info(f"Dry-run for {db_type} migrations")

        # Scan capabilities
        all_metadata = self.scanner.scan_capabilities()
        db_metadata = [m for m in all_metadata if m.db_type == db_type]

        if not db_metadata:
            return {"status": "no_migrations", "migrations": []}

        # Resolve dependencies
        try:
            sorted_metadata = self.dependency_resolver.topological_sort(db_metadata)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        # Alembic stores current heads in alembic_version, not every historical
        # revision that has already been traversed. Build the full applied
        # ancestry from the current heads before deciding what is still pending.
        current_revisions = set(self._get_current_revisions(db_type))
        applied_revisions = self._get_applied_revisions(db_type, current_revisions)
        runtime_known_revisions = self._get_runtime_known_revisions(db_type)

        # Build migration plan
        plan = []
        ignored = []
        for metadata in sorted_metadata:
            for revision in metadata.revisions:
                if runtime_known_revisions and revision not in runtime_known_revisions:
                    ignored.append({
                        "capability": metadata.capability_code,
                        "revision": revision,
                        "status": "not_in_runtime_scripts",
                    })
                    continue
                if revision not in applied_revisions:
                    plan.append({
                        "capability": metadata.capability_code,
                        "revision": revision,
                        "status": "pending"
                    })

        return {
            "status": "success",
            "current_revision": self._format_current_revisions(current_revisions),
            "current_revisions": sorted(current_revisions),
            "applied_revisions": sorted(applied_revisions),
            "migrations": plan,
            "ignored_migrations": ignored,
        }

    def apply(self, db_type: str, dry_run: bool = False) -> Dict:
        """Apply pending migrations for a database type."""
        if dry_run:
            return self.dry_run(db_type)

        logger.info(f"Applying {db_type} migrations")

        # Validate environment
        env_requirements = self._get_env_requirements(db_type)
        validation_results = self.validator.validate_environment(db_type, env_requirements)

        failed_validations = [k for k, v in validation_results.items() if not v]
        if failed_validations:
            return {
                "status": "validation_failed",
                "failed_checks": failed_validations,
                "validation_results": validation_results
            }

        # Get migration plan
        plan_result = self.dry_run(db_type)
        if plan_result["status"] != "success":
            return plan_result

        migrations = plan_result["migrations"]
        if not migrations:
            return {"status": "up_to_date", "migrations_applied": 0}

        # Execute migrations using Alembic
        # Use 'upgrade heads' to apply all pending migrations, including multiple heads
        alembic_config = self.alembic_configs[db_type]

        try:
            # Run alembic upgrade to heads (applies all pending migrations, handles multiple heads)
            result = self._run_alembic_upgrade(alembic_config, "heads")
            if result:
                return {
                    "status": "completed",
                    "migrations_applied": len(migrations),
                    "results": [{"status": "applied"} for _ in migrations]
                }
            else:
                return {
                    "status": "failed",
                    "migrations_applied": 0,
                    "error": "Alembic upgrade failed"
                }
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            return {
                "status": "failed",
                "migrations_applied": 0,
                "error": str(e)
            }

    def status(self, db_type: str) -> Dict:
        """Get migration status for a database type."""
        current_revisions = set(self._get_current_revisions(db_type))
        plan_result = self.dry_run(db_type)

        return {
            "db_type": db_type,
            "current_revision": self._format_current_revisions(current_revisions),
            "current_revisions": sorted(current_revisions),
            "pending_migrations": len(plan_result.get("migrations", [])),
            "migration_plan": plan_result
        }

    def _format_current_revisions(self, revisions: set[str]) -> str | None:
        if not revisions:
            return None
        if len(revisions) == 1:
            return next(iter(revisions))
        return ", ".join(sorted(revisions))

    def _get_current_revisions(self, db_type: str) -> list[str]:
        """Get live Alembic revisions from the target database."""
        try:
            from sqlalchemy import create_engine, text

            if db_type == "postgres":
                from app.database.config import get_postgres_url_core

                db_url = get_postgres_url_core()
            elif db_type == "sqlite":
                backend_dir = Path(__file__).parent.parent.parent.parent
                db_url = f"sqlite:///{(backend_dir.parent / 'data' / 'mindscape.db').absolute()}"
            else:
                logger.warning(f"Unsupported db_type for revision lookup: {db_type}")
                return []

            engine = create_engine(db_url)
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                ).fetchall()
            return [str(row[0]) for row in rows]
        except Exception as e:
            logger.warning(f"Could not get current revisions for {db_type}: {e}")
            return []

    def _get_runtime_known_revisions(self, db_type: str) -> set[str]:
        script_dir = self._load_script_directory(db_type)
        if script_dir is None:
            return set()

        try:
            return {
                rev.revision
                for rev in script_dir.walk_revisions()
                if getattr(rev, "revision", None)
            }
        except Exception as e:
            logger.warning(f"Could not enumerate runtime revisions for {db_type}: {e}")
            return set()

    def _get_applied_revisions(self, db_type: str, current_heads: set[str] | None = None) -> set[str]:
        current_heads = set(current_heads or self._get_current_revisions(db_type))
        if not current_heads:
            return set()

        script_dir = self._load_script_directory(db_type)
        if script_dir is None:
            return current_heads

        applied: set[str] = set()
        for head in current_heads:
            try:
                for rev in script_dir.iterate_revisions(head, "base"):
                    revision = getattr(rev, "revision", None)
                    if revision:
                        applied.add(revision)
            except Exception as e:
                logger.warning(
                    "Could not resolve revision ancestry for %s head %s: %s",
                    db_type,
                    head,
                    e,
                )
                applied.add(head)
        return applied

    def _load_script_directory(self, db_type: str) -> ScriptDirectory | None:
        alembic_config = self.alembic_configs.get(db_type)
        if alembic_config is None:
            logger.warning(f"No alembic config registered for db_type {db_type}")
            return None

        try:
            config = Config(alembic_config.as_posix())

            script_location = config.get_main_option("script_location")
            if script_location and not Path(script_location).is_absolute():
                config.set_main_option(
                    "script_location",
                    (alembic_config.parent / script_location).resolve().as_posix(),
                )

            version_locations = config.get_main_option("version_locations")
            if version_locations:
                resolved_locations = []
                for location in version_locations.split(os.pathsep):
                    location = location.strip()
                    if not location:
                        continue
                    if Path(location).is_absolute():
                        resolved_locations.append(location)
                    else:
                        resolved_locations.append(
                            (alembic_config.parent / location).resolve().as_posix()
                        )
                if resolved_locations:
                    config.set_main_option("version_locations", os.pathsep.join(resolved_locations))

            return ScriptDirectory.from_config(config)
        except Exception as e:
            logger.warning(f"Could not load script directory for {db_type}: {e}")
            return None

    def _run_alembic_upgrade(self, alembic_config: Path, revision: str) -> bool:
        """Run Alembic upgrade to a specific revision or 'head'."""
        backend_dir = alembic_config.parent
        backend_path = str(backend_dir)
        config_path = alembic_config.as_posix()

        # Use subprocess with explicit Python path manipulation via environment
        # This avoids the module import conflict with /app/backend/alembic directory
        env = os.environ.copy()
        # Remove /app/backend from PYTHONPATH if present, keep only site-packages
        pythonpath_parts = env.get('PYTHONPATH', '').split(':') if env.get('PYTHONPATH') else []
        pythonpath_parts = [p for p in pythonpath_parts if '/app/backend' not in p]
        # Add backend only for app imports, but after site-packages
        pythonpath_parts.append(str(backend_dir))
        env['PYTHONPATH'] = ':'.join(pythonpath_parts)

        # Use a Python script that properly sets up the environment
        script = f"""
import sys
import os
from pathlib import Path

# Remove /app/backend from path to avoid alembic directory conflict
backend_path = '{backend_path}'
while backend_path in sys.path:
    sys.path.remove(backend_path)

# Ensure site-packages is first
import site
site_packages = site.getsitepackages()
for sp in site_packages:
    if sp in sys.path:
        sys.path.remove(sp)
    sys.path.insert(0, sp)

# Add backend back for app imports
sys.path.append(backend_path)

# Change to backend directory
os.chdir(backend_path)

# Now import and execute
from alembic.config import Config
from alembic import command

config = Config('{config_path}')
command.upgrade(config, '{revision}')
"""

        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(backend_dir),
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
                env=env
            )
            logger.info(f"Migration upgrade to {revision} completed successfully")
            if result.stdout:
                logger.info(f"Alembic stdout: {result.stdout}")
            if result.stderr:
                # Check for revision conflict warnings
                # Only treat as error if the conflicting revision is the one we're trying to execute
                if "Revision" in result.stderr and "is present more than once" in result.stderr:
                    import re
                    conflict_match = re.search(r"Revision (\d+) is present more than once", result.stderr)
                    if conflict_match:
                        conflicting_revision = conflict_match.group(1)
                        # Only fail if the conflict is with the revision we're trying to execute
                        if conflicting_revision == revision:
                            logger.error(f"Migration revision conflict detected in stderr: {result.stderr}")
                            error_msg = f"Migration revision ID conflict: Revision {conflicting_revision} is present more than once. This will prevent migrations from executing correctly."
                            logger.error(error_msg)
                            return False
                        else:
                            # Conflict is with other capability's revision, log warning but continue
                            logger.warning(f"Revision conflict detected for {conflicting_revision} (not the current revision {revision}), continuing...")
                logger.warning(f"Alembic stderr: {result.stderr}")
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"Migration upgrade to {revision} timed out after 5 minutes")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Migration upgrade to {revision} failed: {e.stderr}")
            if e.stdout:
                logger.error(f"Alembic stdout: {e.stdout}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during migration: {e}")
            return False

    def _get_env_requirements(self, db_type: str) -> Dict:
        """Get environment requirements for validation."""
        if db_type == "postgres":
            from app.database.config import get_postgres_url_core
            return {
                "postgres_url": get_postgres_url_core(),
                "environment_requirements": {
                    "postgres": {
                        "extensions": ["vector"],
                        "min_version": "12.0"
                    }
                }
            }
        elif db_type == "sqlite":
            from pathlib import Path
            backend_dir = Path(__file__).parent.parent.parent.parent
            data_dir = backend_dir.parent / "data"
            return {
                "sqlite_path": str(data_dir / "mindscape.db")
            }
        return {}
