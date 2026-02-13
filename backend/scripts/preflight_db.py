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
import sys
import time
import subprocess


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


def verify_critical_tables():
    """Verify that critical PostgreSQL tables exist. Returns True if all OK."""
    try:
        import psycopg2
    except ImportError:
        print("[preflight] psycopg2 not available, skipping table verification")
        return True  # Can't verify, let startup_event handle it

    critical_tables = ["profiles", "workspaces", "system_settings", "user_configs"]

    pg_host = os.getenv("POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres"))
    pg_port = int(os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432")))
    pg_user = os.getenv("POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape"))
    pg_pass = os.getenv(
        "POSTGRES_CORE_PASSWORD",
        os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
    )
    core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")

    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_pass,
            dbname=core_db,
            connect_timeout=5,
        )
        cur = conn.cursor()
        missing = []
        for table in critical_tables:
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_name = %s AND table_schema = 'public'"
                ")",
                (table,),
            )
            if not cur.fetchone()[0]:
                missing.append(table)
        cur.close()
        conn.close()

        if missing:
            print(f"[preflight] CRITICAL: Missing tables: {', '.join(missing)}")
            return False
        else:
            print(f"[preflight] All {len(critical_tables)} critical tables verified")
            return True

    except Exception as e:
        print(f"[preflight] Table verification failed: {e}")
        return False


if __name__ == "__main__":
    db_ok = ensure_databases()
    if db_ok:
        migration_ok = run_migrations()
        if not migration_ok:
            print("[preflight] WARNING: Alembic migration returned failure")
            # Clean up stale alembic_version entries if tables are missing
            # This handles the case where a previous failed migration left
            # partial state (e.g. some tables created, version stamped, but
            # subsequent migrations failed). Without cleanup, Alembic would
            # skip already-stamped migrations and still fail.
            try:
                import psycopg2
                from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

                pg_host = os.getenv(
                    "POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres")
                )
                pg_port = int(
                    os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432"))
                )
                pg_user = os.getenv(
                    "POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape")
                )
                pg_pass = os.getenv(
                    "POSTGRES_CORE_PASSWORD",
                    os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
                )
                core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")

                conn = psycopg2.connect(
                    host=pg_host,
                    port=pg_port,
                    user=pg_user,
                    password=pg_pass,
                    dbname=core_db,
                    connect_timeout=5,
                )
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = conn.cursor()

                # Check if alembic_version exists and has entries
                cur.execute(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_name = 'alembic_version' AND table_schema = 'public'"
                    ")"
                )
                if cur.fetchone()[0]:
                    cur.execute("SELECT version_num FROM alembic_version")
                    versions = [r[0] for r in cur.fetchall()]
                    if versions:
                        print(
                            f"[preflight] Cleaning stale alembic_version entries: {versions}"
                        )
                        cur.execute("DELETE FROM alembic_version")

                cur.close()
                conn.close()

                # Retry migration after cleanup
                print("[preflight] Retrying Alembic migration after cleanup...")
                migration_ok = run_migrations()
                if migration_ok:
                    print("[preflight] Migration succeeded on retry")
            except Exception as e:
                print(f"[preflight] Cleanup/retry failed: {e}")
    else:
        print("[preflight] Skipping migrations since database setup failed")

    # Verify critical tables exist regardless of migration result
    tables_ok = verify_critical_tables()
    if not tables_ok:
        print("[preflight] FATAL: Critical tables missing after migration!")
        print("[preflight] The application cannot start without these tables.")
        print("[preflight] Check PostgreSQL connection and Alembic configuration.")
        sys.exit(1)

    print("[preflight] Preflight complete, starting application...")
