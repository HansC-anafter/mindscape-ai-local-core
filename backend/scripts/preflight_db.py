#!/usr/bin/env python3
"""
Pre-flight database bootstrap: ensures required databases AND tables
exist before the main application starts.

This runs BEFORE uvicorn imports main.py, which is necessary because
MindscapeStore() is instantiated at module import time and will crash
if the database or tables don't exist.

Steps:
  1. Connect to default 'postgres' DB and create mindscape_core / mindscape_vectors
  2. Install pgvector extension in vector DB
  3. Run Alembic migrations to create/update tables
"""
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def should_skip_migrations() -> bool:
    if _parse_bool(os.getenv("MINDSCAPE_PREFLIGHT_SKIP_MIGRATIONS")):
        return True
    role = str(os.getenv("MINDSCAPE_BACKEND_ROLE", "")).strip().lower()
    if role == "control":
        return _parse_bool(os.getenv("MINDSCAPE_CONTROL_PLANE_SKIP_MIGRATIONS", "1"))
    if role in {"execution", "stable"}:
        execution_policy = os.getenv("MINDSCAPE_EXECUTION_PLANE_SKIP_MIGRATIONS")
        if execution_policy is not None:
            return _parse_bool(execution_policy)
        return True
    return False


def ensure_databases():
    """Create missing databases by connecting to the default 'postgres' DB."""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        print("[preflight] psycopg2 not available, skipping DB check")
        return False

    pg_host = os.getenv("POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres"))
    pg_port = int(os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432")))
    pg_user = os.getenv("POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape"))
    pg_pass = os.getenv(
        "POSTGRES_CORE_PASSWORD",
        os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
    )
    core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")
    vector_db = os.getenv("POSTGRES_VECTOR_DB", "mindscape_vectors")

    if pg_host == "pgbouncer" or pg_port == 6432:
        from backend.scripts.preflight_db_core import run_bounded_database_probe

        for db_name in [core_db, vector_db]:
            def _probe_database():
                conn = psycopg2.connect(
                    host=pg_host,
                    port=pg_port,
                    user=pg_user,
                    password=pg_pass,
                    dbname=db_name,
                    connect_timeout=5,
                )
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                conn.close()
                return True

            probe, _ = run_bounded_database_probe(_probe_database)
            if probe.state.value != "ready":
                print(
                    "[preflight] PgBouncer database check did not become ready: "
                    f"database={db_name} state={probe.state.value} "
                    f"attempts={probe.attempts} code={probe.failure_code}"
                )
                return False
            print(f"[preflight] Database '{db_name}' reachable via PgBouncer")

        try:
            vconn = psycopg2.connect(
                host=pg_host,
                port=pg_port,
                user=pg_user,
                password=pg_pass,
                dbname=vector_db,
                connect_timeout=5,
            )
            vconn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            vcur = vconn.cursor()
            vcur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            vcur.close()
            vconn.close()
            print("[preflight] pgvector extension verified")
        except Exception as ext_err:
            print(f"[preflight] pgvector extension check failed: {ext_err}")
            return False

        print("[preflight] Database preflight check passed")
        return True

    max_retries = 15
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=pg_host,
                port=pg_port,
                user=pg_user,
                password=pg_pass,
                dbname="postgres",
                connect_timeout=5,
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()

            for db_name in [core_db, vector_db]:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"[preflight] Created missing database: {db_name}")
                else:
                    print(f"[preflight] Database '{db_name}' exists")

            cur.close()
            conn.close()

            # Ensure pgvector extension in vector database
            try:
                vconn = psycopg2.connect(
                    host=pg_host,
                    port=pg_port,
                    user=pg_user,
                    password=pg_pass,
                    dbname=vector_db,
                    connect_timeout=5,
                )
                vconn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                vcur = vconn.cursor()
                vcur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                vcur.close()
                vconn.close()
                print("[preflight] pgvector extension verified")
            except Exception as ext_err:
                print(f"[preflight] pgvector extension check failed: {ext_err}")
                return False

            print("[preflight] Database preflight check passed")
            return True

        except Exception as e:
            print(
                f"[preflight] PostgreSQL not ready (attempt {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(min(2 ** (attempt - 1), 10))
            else:
                print("[preflight] WARNING: Could not verify databases after retries")
                return False

    return False


def run_migrations():
    """Run Alembic migrations to ensure all tables exist."""
    from backend.app.services.runtime_database_incident_gate import (
        RuntimeDatabaseMutationBlocked,
        require_runtime_database_mutation_allowed,
    )

    try:
        require_runtime_database_mutation_allowed("startup_alembic_migration")
    except RuntimeDatabaseMutationBlocked as exc:
        print(
            "[preflight] Migration blocked by runtime database incident gate: "
            f"reason={exc.decision.reason} incident_id={exc.decision.incident_id}"
        )
        return False

    # Determine paths inside Docker container
    backend_dir = "/app/backend"
    alembic_ini = os.path.join(backend_dir, "alembic.postgres.ini")

    if not os.path.exists(alembic_ini):
        # Try relative path for local development
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(script_dir)
        alembic_ini = os.path.join(backend_dir, "alembic.postgres.ini")

    if not os.path.exists(alembic_ini):
        print(
            f"[preflight] Alembic config not found at {alembic_ini}, skipping migrations"
        )
        return False

    print(f"[preflight] Running Alembic migrations from {backend_dir}...")
    try:
        result = subprocess.run(
            ["alembic", "-c", alembic_ini, "upgrade", "heads"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print("[preflight] Alembic migrations completed successfully")
            if result.stderr:
                # Alembic logs to stderr
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"[preflight] {line.strip()}")
            return True
        else:
            print(f"[preflight] Alembic migration failed (exit {result.returncode})")
            if result.stdout:
                print(f"[preflight] stdout: {result.stdout[:5000]}")
            if result.stderr:
                print(f"[preflight] stderr: {result.stderr[:5000]}")
            return False
    except subprocess.TimeoutExpired:
        print("[preflight] Alembic migration timed out after 120s")
        return False
    except FileNotFoundError:
        print("[preflight] alembic command not found, skipping migrations")
        return False
    except Exception as e:
        print(f"[preflight] Migration error: {e}")
        return False


def verify_critical_tables_state():
    """Return a typed result; connection failure is never called schema missing."""
    from backend.scripts.preflight_db_core import (
        DatabaseProbeResult,
        DatabaseProbeState,
        find_missing_public_relations,
        required_relations_for_backend_role,
        run_bounded_database_probe,
    )

    try:
        import psycopg2
    except ImportError:
        print("[preflight] psycopg2 not available, skipping table verification")
        return DatabaseProbeResult(
            state=DatabaseProbeState.UNAVAILABLE,
            attempts=0,
            elapsed_seconds=0.0,
            failure_code="psycopg2_unavailable",
        )

    backend_role = str(os.getenv("MINDSCAPE_BACKEND_ROLE", "")).strip().lower()
    required_relations = required_relations_for_backend_role(backend_role)

    pg_host = os.getenv("POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres"))
    pg_port = int(os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432")))
    pg_user = os.getenv("POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape"))
    pg_pass = os.getenv(
        "POSTGRES_CORE_PASSWORD",
        os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
    )
    core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")

    def _probe_tables():
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_pass,
            dbname=core_db,
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                return find_missing_public_relations(cur, required_relations)
        finally:
            conn.close()

    probe, missing = run_bounded_database_probe(_probe_tables)
    if probe.state is not DatabaseProbeState.READY:
        print(
            "[preflight] Table catalog unavailable: "
            f"state={probe.state.value} attempts={probe.attempts} "
            f"code={probe.failure_code}"
        )
        return probe
    if missing:
        print(f"[preflight] CRITICAL: Missing tables: {', '.join(missing)}")
        return DatabaseProbeResult(
            state=DatabaseProbeState.SCHEMA_MISSING,
            attempts=probe.attempts,
            elapsed_seconds=probe.elapsed_seconds,
            missing_tables=tuple(missing),
        )
    role_label = backend_role or "unspecified"
    print(
        f"[preflight] All {len(required_relations)} critical relations verified "
        f"for backend role '{role_label}'"
    )
    return probe


def verify_critical_tables():
    """Compatibility bool facade for callers that do not need typed exits."""
    from backend.scripts.preflight_db_core import DatabaseProbeState

    return verify_critical_tables_state().state is DatabaseProbeState.READY


def verify_host_resource_schema_contract_state() -> dict:
    """Run host-resource schema contract readiness for startup fail-closed validation."""
    from backend.app.services.host_resources.schema_readiness import (
        check_host_resource_schema_readiness,
    )

    return check_host_resource_schema_readiness()


def _print_host_resource_drift(report: dict) -> None:
    missing_tables = ", ".join(report.get("missing_tables", ()))
    if missing_tables:
        print(f"[preflight] Host-resource missing tables: {missing_tables}")
    missing_indexes = ", ".join(report.get("missing_indexes", ()))
    if missing_indexes:
        print(f"[preflight] Host-resource missing indexes: {missing_indexes}")
    missing_columns = report.get("missing_columns", {})
    if isinstance(missing_columns, dict):
        for table_name in sorted(missing_columns):
            columns = missing_columns[table_name]
            if columns:
                print(
                    f"[preflight] Host-resource missing columns in "
                    f"{table_name}: {', '.join(sorted(columns))}"
                )


if __name__ == "__main__":
    db_ok = ensure_databases()
    if db_ok:
        if should_skip_migrations():
            print("[preflight] Skipping Alembic migrations by runtime policy")
        else:
            migration_ok = run_migrations()
            if not migration_ok:
                print("[preflight] WARNING: Alembic migration returned failure")
                print(
                    "[preflight] Alembic history is append-only; diagnose the graph "
                    "and apply a corrective revision before retrying."
                )
    else:
        print("[preflight] Skipping migrations since database setup failed")

    # Verify critical tables exist regardless of migration result
    from backend.scripts.preflight_db_core import DatabaseProbeState

    table_probe = verify_critical_tables_state()
    if table_probe.state is DatabaseProbeState.SCHEMA_MISSING:
        print("[preflight] FATAL: Critical tables missing after migration!")
        print("[preflight] The application cannot start without these tables.")
        print("[preflight] Check PostgreSQL connection and Alembic configuration.")
        sys.exit(1)
    if table_probe.state is not DatabaseProbeState.READY:
        print(
            "[preflight] FATAL: Database remained unavailable after bounded wait; "
            f"state={table_probe.state.value} code={table_probe.failure_code}"
        )
        sys.exit(75)

    host_resource_schema = verify_host_resource_schema_contract_state()
    if host_resource_schema.get("migration_applied") and not host_resource_schema.get("ready"):
        print(
            "[preflight] FATAL: Host-resource schema drift detected after migration."
        )
        print(
            "[preflight] Revision was recorded as applied but required "
            "host-resource schema objects are missing."
        )
        _print_host_resource_drift(host_resource_schema)
        print(
            "[preflight] Run repair/reconciliation flow before starting "
            "application."
        )
        sys.exit(1)

    print("[preflight] Preflight complete, starting application...")
