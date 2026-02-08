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
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.migrations import MigrationOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def status_command(db_type: str):
    """Check migration status for a database type."""
    capabilities_root = backend_dir / "app" / "capabilities"
    alembic_configs = {
        "postgres": backend_dir / "alembic.ini",
    }

    orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)
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
    capabilities_root = backend_dir / "app" / "capabilities"
    alembic_configs = {
        "postgres": backend_dir / "alembic.ini",
    }

    orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)
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


def apply_command(db_type: str, dry_run: bool = False):
    """Apply pending migrations for a database type."""
    capabilities_root = backend_dir / "app" / "capabilities"
    alembic_configs = {
        "postgres": backend_dir / "alembic.ini",
    }

    orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

    if dry_run:
        return dry_run_command(db_type)

    result = orchestrator.apply(db_type, dry_run=False)

    print(f"\nApply Migrations for {db_type.upper()}")
    print("=" * 60)
    print(f"Status: {result.get('status')}")

    if result.get('status') == 'completed':
        print(f"Migrations Applied: {result.get('migrations_applied', 0)}")
    elif result.get('status') == 'validation_failed':
        print(f"Validation Failed: {result.get('failed_checks')}")
        print(f"Validation Results: {result.get('validation_results')}")
    elif result.get('status') == 'error':
        print(f"Error: {result.get('error')}")
    elif result.get('status') == 'up_to_date':
        print("Database is up to date.")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Migration management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check migration status')
    status_parser.add_argument('--db', choices=['postgres'], required=True,
                               help='Database type')

    # Dry-run command
    dry_run_parser = subparsers.add_parser('dry-run', help='Perform dry-run')
    dry_run_parser.add_argument('--db', choices=['postgres'], required=True,
                                help='Database type')

    # Apply command
    apply_parser = subparsers.add_parser('apply', help='Apply migrations')
    apply_parser.add_argument('--db', choices=['postgres'], required=True,
                             help='Database type')
    apply_parser.add_argument('--dry-run', action='store_true',
                             help='Perform dry-run instead of applying')

    args = parser.parse_args()

    if args.command == 'status':
        status_command(args.db)
    elif args.command == 'dry-run':
        dry_run_command(args.db)
    elif args.command == 'apply':
        apply_command(args.db, dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
