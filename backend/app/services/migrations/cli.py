#!/usr/bin/env python3
"""
CLI tool for migration management.
Provides commands to check status, dry-run, and apply migrations.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.migrations import MigrationOrchestrator
from app.services.migrations.database_plan import authoritative_alembic_configs
from app.services.migrations.head_normalizer import (
    MigrationHeadNormalizationFacade,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _build_orchestrator() -> MigrationOrchestrator:
    """Facade seam for canonical runtime migration paths and configuration."""
    capabilities_root = backend_dir / "app" / "capabilities"
    alembic_configs = authoritative_alembic_configs(backend_dir)
    return MigrationOrchestrator(capabilities_root, alembic_configs)


def status_command(db_type: str):
    """Check migration status for a database type."""
    orchestrator = _build_orchestrator()
    result = orchestrator.status(db_type)

    print(f"\nMigration Status for {db_type.upper()}")
    print("=" * 60)
    print(f"Current Revision: {result.get('current_revision', 'None')}")
    print(f"Pending Migrations: {result.get('pending_migrations', 0)}")

    plan = result.get('migration_plan', {})
    if plan.get('migrations'):
        print("\nPending Migrations:")
        for migration in plan['migrations']:
            print(f"  - {migration.get('capability')}: {migration.get('revision')}")
    else:
        print("\nNo pending migrations.")


def dry_run_command(db_type: str):
    """Perform a dry-run to show what migrations would be executed."""
    orchestrator = _build_orchestrator()
    result = orchestrator.dry_run(db_type)

    print(f"\nDry-Run for {db_type.upper()} Migrations")
    print("=" * 60)
    print(f"Status: {result.get('status')}")

    if result.get('status') == 'success':
        print(f"Current Revision: {result.get('current_revision', 'None')}")
        migrations = result.get('migrations', [])
        print(f"Pending Migrations: {len(migrations)}")

        if migrations:
            print("\nMigrations to be applied:")
            for migration in migrations:
                print(f"  - {migration.get('capability')}: {migration.get('revision')}")
        else:
            print("\nNo pending migrations.")
    elif result.get('status') == 'error':
        print(f"Error: {result.get('error')}")
    elif result.get('status') == 'no_migrations':
        print("No migrations found for this database type.")


def apply_command(
    db_type: str,
    dry_run: bool = False,
    revision: str | None = None,
):
    """Apply pending migrations for a database type."""
    orchestrator = _build_orchestrator()

    if dry_run and revision:
        if db_type == "vector":
            result = orchestrator.apply_vector_revision_after_core_ready(
                revision,
                dry_run=True,
            )
        else:
            result = orchestrator.plan_revision(db_type, revision)
        print(f"\nTargeted Dry-Run for {db_type.upper()} Migrations")
        print("=" * 60)
        print(f"Status: {result.get('status')}")
        print(f"Target Revision: {result.get('target_revision', revision)}")
        print(f"Pending Migrations: {result.get('migrations_pending', 0)}")
        for pending_revision in result.get('revisions', []):
            print(f"  - {pending_revision}")
        if result.get('error'):
            print(f"Error: {result.get('error')}")
        return
    if dry_run:
        return dry_run_command(db_type)

    if revision:
        if db_type == "vector":
            result = orchestrator.apply_vector_revision_after_core_ready(
                revision,
                dry_run=False,
            )
        else:
            result = orchestrator.apply_revision(db_type, revision)
    else:
        result = orchestrator.apply(db_type, dry_run=False)

    print(f"\nApply Migrations for {db_type.upper()}")
    print("=" * 60)
    print(f"Status: {result.get('status')}")

    if result.get('status') == 'completed':
        print(f"Migrations Applied: {result.get('migrations_applied', 0)}")
        if result.get('target_revision'):
            print(f"Target Revision: {result.get('target_revision')}")
    elif result.get('status') == 'validation_failed':
        print(f"Validation Failed: {result.get('failed_checks')}")
        print(f"Validation Results: {result.get('validation_results')}")
    elif result.get('status') == 'error':
        print(f"Error: {result.get('error')}")
    elif result.get('status') == 'up_to_date':
        print("Database is up to date.")
    elif result.get('status') in {
        'invalid_revision',
        'revision_catalog_unavailable',
        'unsupported_database',
        'failed',
    }:
        print(f"Error: {result.get('error')}")


def normalize_heads_command(db_type: str, *, apply: bool) -> None:
    """Plan or apply removal of graph-proven redundant current heads."""

    if db_type != "postgres":
        raise SystemExit("Only PostgreSQL head normalization is supported")
    orchestrator = _build_orchestrator()
    script_directory = orchestrator._load_script_directory(db_type)
    if script_directory is None:
        raise SystemExit("Runtime migration catalog is unavailable")
    from app.database.config import get_postgres_url_core_session

    facade = MigrationHeadNormalizationFacade(
        script_directory=script_directory,
        postgres_url=get_postgres_url_core_session(),
    )
    plan = facade.plan(orchestrator._get_current_revisions(db_type))
    print("\nMigration Head Normalization")
    print("=" * 60)
    for key, value in plan.model_dump().items():
        print(f"{key}: {value}")
    if plan.status == "blocked_unresolved":
        raise SystemExit(2)
    if not apply or plan.status == "clean":
        return
    result = facade.apply(plan)
    print(f"applied_status: {result.status}")
    print(f"retained_revisions: {result.retained_revisions}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Migration management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check migration status')
    status_parser.add_argument('--db', choices=['postgres', 'vector'], required=True,
                               help='Database type')

    # Dry-run command
    dry_run_parser = subparsers.add_parser('dry-run', help='Perform dry-run')
    dry_run_parser.add_argument('--db', choices=['postgres', 'vector'], required=True,
                                help='Database type')

    # Apply command
    apply_parser = subparsers.add_parser('apply', help='Apply migrations')
    apply_parser.add_argument('--db', choices=['postgres', 'vector'], required=True,
                             help='Database type')
    apply_parser.add_argument('--dry-run', action='store_true',
                             help='Perform dry-run instead of applying')
    apply_parser.add_argument(
        '--revision',
        help='Apply one exact revision target and only its unapplied ancestors',
    )
    normalize_parser = subparsers.add_parser(
        "normalize-heads",
        help="Remove only runtime-graph-proven redundant current heads",
    )
    normalize_parser.add_argument(
        "--db",
        choices=["postgres"],
        required=True,
        help="Database type",
    )
    normalize_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the exact compare-and-swap normalization plan",
    )

    args = parser.parse_args()

    if args.command == 'status':
        status_command(args.db)
    elif args.command == 'dry-run':
        dry_run_command(args.db)
    elif args.command == 'apply':
        apply_command(args.db, dry_run=args.dry_run, revision=args.revision)
    elif args.command == "normalize-heads":
        normalize_heads_command(args.db, apply=args.apply)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
