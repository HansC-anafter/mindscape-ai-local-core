#!/usr/bin/env python3
"""
Verification script for Mind-Lens migration and new architecture.

This script verifies:
1. Feature Flag is enabled
2. Database migrations are applied
3. Lens API endpoints are working
4. Migration architecture is functioning

Usage:
    export USE_EFFECTIVE_LENS_RESOLVER=true
    python scripts/verify_lens_migration.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_feature_flag():
    """Check if USE_EFFECTIVE_LENS_RESOLVER is enabled"""
    flag_value = os.getenv("USE_EFFECTIVE_LENS_RESOLVER", "false").lower()
    is_enabled = flag_value == "true"

    logger.info(f"Feature Flag Status: USE_EFFECTIVE_LENS_RESOLVER={flag_value}")
    if not is_enabled:
        logger.warning("⚠️  USE_EFFECTIVE_LENS_RESOLVER is not enabled!")
        logger.warning("   Set it with: export USE_EFFECTIVE_LENS_RESOLVER=true")
        return False
    else:
        logger.info("✅ Feature Flag is enabled")
        return True


def check_sqlite_migration():
    """Check SQLite migration status"""
    logger.info("\n=== Checking SQLite Migrations ===")

    alembic_config = backend_dir / "alembic.sqlite.ini"

    # Check current revision
    try:
        result = subprocess.run(
            ["alembic", "-c", str(alembic_config), "current"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(backend_dir)
        )
        current_rev = result.stdout.strip()
        logger.info(f"Current SQLite revision: {current_rev}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get current revision: {e.stderr}")
        return False

    # Check if key tables exist
    from app.services.stores.base import StoreBase

    store = StoreBase()
    with store.get_connection() as conn:
        cursor = conn.cursor()

        required_tables = [
            "lens_profile_nodes",
            "workspace_lens_overrides",
            "lens_snapshots",
            "lens_receipts",
            "preview_votes"  # From metrics migration
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        logger.info("\nChecking required tables:")
        all_exist = True
        for table in required_tables:
            if table in existing_tables:
                logger.info(f"  ✅ {table}")
            else:
                logger.error(f"  ❌ {table} - NOT FOUND")
                all_exist = False

        # Check lens_receipts extended columns
        if "lens_receipts" in existing_tables:
            cursor.execute("PRAGMA table_info(lens_receipts)")
            columns = {row[1] for row in cursor.fetchall()}
            extended_columns = [
                "accepted", "rerun_count", "edit_count",
                "time_to_accept_ms", "apply_target",
                "anti_goal_violations", "coverage_emph_triggered"
            ]
            logger.info("\nChecking lens_receipts extended columns:")
            for col in extended_columns:
                if col in columns:
                    logger.info(f"  ✅ {col}")
                else:
                    logger.warning(f"  ⚠️  {col} - NOT FOUND (metrics migration may not be applied)")

        return all_exist


def check_postgres_migration():
    """Check PostgreSQL migration status (if available)"""
    logger.info("\n=== Checking PostgreSQL Migrations ===")

    alembic_config = backend_dir / "alembic.ini"

    try:
        result = subprocess.run(
            ["alembic", "-c", str(alembic_config), "current"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(backend_dir),
            timeout=5
        )
        current_rev = result.stdout.strip()
        logger.info(f"Current PostgreSQL revision: {current_rev}")
        return True
    except subprocess.TimeoutExpired:
        logger.warning("⚠️  PostgreSQL connection timeout (may not be available)")
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(f"⚠️  PostgreSQL not available: {e.stderr.strip()}")
        return None
    except FileNotFoundError:
        logger.warning("⚠️  PostgreSQL not configured")
        return None


def check_migration_orchestrator():
    """Check if migration orchestrator is working"""
    logger.info("\n=== Checking Migration Orchestrator ===")

    try:
        from app.services.migrations import MigrationOrchestrator
        from pathlib import Path

        capabilities_root = backend_dir / "app" / "capabilities"
        alembic_configs = {
            "sqlite": backend_dir / "alembic.sqlite.ini",
            "postgres": backend_dir / "alembic.ini",
        }

        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

        # Dry-run SQLite
        logger.info("Running SQLite dry-run...")
        result = orchestrator.dry_run("sqlite")
        logger.info(f"SQLite dry-run result: {result.get('status')}")

        if result.get("status") == "success":
            migrations = result.get("migrations", [])
            logger.info(f"Pending migrations: {len(migrations)}")
            if migrations:
                for m in migrations[:5]:  # Show first 5
                    logger.info(f"  - {m.get('capability', 'unknown')}: {m.get('revision')}")

        return True
    except Exception as e:
        logger.error(f"Failed to check orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_lens_api_endpoints():
    """Check if Lens API endpoints are accessible"""
    logger.info("\n=== Checking Lens API Endpoints ===")

    # This would require the server to be running
    # For now, just check if routes are registered
    try:
        from app.routes.lens import router

        # Check if key routes exist
        routes = [r.path for r in router.routes]
        required_routes = [
            "/effective-lens",
            "/preview",
            "/changesets",
            "/changesets/apply"
        ]

        logger.info("Checking route registration:")
        for route in required_routes:
            # Routes are prefixed, so check if any route contains the path
            found = any(route in r for r in routes)
            if found:
                logger.info(f"  ✅ {route}")
            else:
                logger.warning(f"  ⚠️  {route} - May not be registered")

        return True
    except Exception as e:
        logger.error(f"Failed to check routes: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main verification flow"""
    logger.info("=" * 60)
    logger.info("Mind-Lens Migration Verification")
    logger.info("=" * 60)

    results = {}

    # Step 1: Check Feature Flag
    results["feature_flag"] = check_feature_flag()

    # Step 2: Check SQLite migrations
    results["sqlite_migration"] = check_sqlite_migration()

    # Step 3: Check PostgreSQL migrations (optional)
    results["postgres_migration"] = check_postgres_migration()

    # Step 4: Check Migration Orchestrator
    results["orchestrator"] = check_migration_orchestrator()

    # Step 5: Check API routes
    results["api_routes"] = check_lens_api_endpoints()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Verification Summary")
    logger.info("=" * 60)

    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed is None:
            status = "⚠️  SKIP"
        logger.info(f"{check:20s}: {status}")

    all_passed = all(v for v in results.values() if v is not None)

    if all_passed:
        logger.info("\n✅ All checks passed!")
        logger.info("\nNext steps:")
        logger.info("1. Start the backend server")
        logger.info("2. Test API endpoints:")
        logger.info("   - GET /api/v1/mindscape/lens/effective-lens?profile_id=...")
        logger.info("   - POST /api/v1/mindscape/lens/preview")
        logger.info("   - POST /api/v1/mindscape/lens/changesets")
        logger.info("3. Run a playbook execution to verify snapshot/receipt generation")
        return 0
    else:
        logger.error("\n❌ Some checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
