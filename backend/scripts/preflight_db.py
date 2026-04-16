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
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.app_bootstrap.startup_contract import (
    capture_phase_duration,
    compute_db_fingerprint,
    new_startup_boot_id,
    write_preflight_contract,
)

_LAST_MIGRATION_FAILURE_DETAILS: str | None = None


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
    global _LAST_MIGRATION_FAILURE_DETAILS
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
            _LAST_MIGRATION_FAILURE_DETAILS = None
            print("[preflight] Alembic migrations completed successfully")
            if result.stderr:
                # Alembic logs to stderr
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        print(f"[preflight] {line.strip()}")
            return True
        else:
            _LAST_MIGRATION_FAILURE_DETAILS = "\n".join(
                part for part in [result.stdout, result.stderr] if part
            )
            print(f"[preflight] Alembic migration failed (exit {result.returncode})")
            if result.stdout:
                print(f"[preflight] stdout: {result.stdout[:5000]}")
            if result.stderr:
                print(f"[preflight] stderr: {result.stderr[:5000]}")
            return False
    except subprocess.TimeoutExpired:
        _LAST_MIGRATION_FAILURE_DETAILS = "timeout"
        print("[preflight] Alembic migration timed out after 120s")
        return False
    except FileNotFoundError:
        _LAST_MIGRATION_FAILURE_DETAILS = "alembic_command_not_found"
        print("[preflight] alembic command not found, skipping migrations")
        return False
    except Exception as e:
        _LAST_MIGRATION_FAILURE_DETAILS = str(e)
        print(f"[preflight] Migration error: {e}")
        return False


def _is_revision_graph_failure(details: str | None) -> bool:
    if not details:
        return False
    patterns = (
        "KeyError:",
        "Revision ",
        "Can't locate revision identified by",
        "is not present",
    )
    return any(pattern in details for pattern in patterns)


def _repair_script_path() -> str:
    script_dir = Path(__file__).resolve().parent
    return str(script_dir / "repair_alembic_state.py")


def _backend_dir() -> str:
    return str(Path(__file__).resolve().parents[1])


def try_repair_alembic_state(apply: bool) -> bool:
    """Run the repo-owned alembic repair helper.

    This is only intended for populated databases whose alembic_version table is
    empty. The helper performs its own sentinel-table validation before
    stamping heads.
    """
    repair_script = _repair_script_path()
    if not os.path.exists(repair_script):
        print(f"[preflight] Alembic repair helper not found at {repair_script}")
        return False

    cmd = [sys.executable, repair_script]
    if apply:
        cmd.append("--apply")

    mode = "apply" if apply else "dry-run"
    print(f"[preflight] Running Alembic repair helper ({mode})...")
    try:
        result = subprocess.run(
            cmd,
            cwd=_backend_dir(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            print(f"[preflight] repair stdout: {result.stdout[:5000]}")
        if result.stderr:
            print(f"[preflight] repair stderr: {result.stderr[:5000]}")

        if result.returncode != 0:
            print(
                f"[preflight] Alembic repair helper failed in {mode} mode "
                f"(exit {result.returncode})"
            )
            return False

        stdout = result.stdout or ""
        if "ALEMBIC_REPAIR_NOOP_ALREADY_STAMPED" in stdout:
            return True
        if not apply and "ALEMBIC_REPAIR_DRY_RUN_OK" in stdout:
            return True
        if apply and "ALEMBIC_REPAIR_STAMPED_VERSIONS" in stdout:
            return True

        print(
            f"[preflight] Alembic repair helper returned success but did not emit "
            f"an expected marker in {mode} mode"
        )
        return False
    except subprocess.TimeoutExpired:
        print(f"[preflight] Alembic repair helper timed out in {mode} mode")
        return False
    except Exception as e:
        print(f"[preflight] Alembic repair helper error in {mode} mode: {e}")
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
    preflight_started = time.monotonic()
    startup_boot_id = new_startup_boot_id()
    db_fingerprint = compute_db_fingerprint()
    phase_timings: dict[str, int] = {}
    repair_dry_run_ok = False
    repair_apply_ok = False
    migration_ok = False
    migration_retry_ok = False

    db_phase_started = time.monotonic()
    db_ok = ensure_databases()
    phase_timings["ensure_databases_ms"] = capture_phase_duration(
        "preflight.ensure_databases",
        db_phase_started,
        print,
        extra={"boot_id": startup_boot_id, "ok": str(db_ok).lower()},
    )

    if db_ok:
        repair_dry_run_started = time.monotonic()
        repair_dry_run_ok = try_repair_alembic_state(apply=False)
        phase_timings["repair_dry_run_ms"] = capture_phase_duration(
            "preflight.repair_dry_run",
            repair_dry_run_started,
            print,
            extra={"boot_id": startup_boot_id, "ok": str(repair_dry_run_ok).lower()},
        )

        if repair_dry_run_ok:
            print(
                "[preflight] Detected populated unstamped Alembic state; "
                "attempting automatic head stamp before upgrade."
            )
            repair_apply_started = time.monotonic()
            repair_apply_ok = try_repair_alembic_state(apply=True)
            phase_timings["repair_apply_ms"] = capture_phase_duration(
                "preflight.repair_apply",
                repair_apply_started,
                print,
                extra={
                    "boot_id": startup_boot_id,
                    "ok": str(repair_apply_ok).lower(),
                },
            )

        migration_started = time.monotonic()
        migration_ok = repair_apply_ok or run_migrations()
        phase_timings["run_migrations_ms"] = capture_phase_duration(
            "preflight.run_migrations",
            migration_started,
            print,
            extra={
                "boot_id": startup_boot_id,
                "ok": str(migration_ok).lower(),
                "mode": "repair_apply_skip" if repair_apply_ok else "alembic_upgrade",
            },
        )
        if not migration_ok:
            print("[preflight] WARNING: Alembic migration returned failure")
            if _is_revision_graph_failure(_LAST_MIGRATION_FAILURE_DETAILS):
                print(
                    "[preflight] Skipping alembic_version cleanup because the Alembic "
                    "revision graph is invalid in this runtime."
                )
            else:
                # Clean up stale alembic_version entries if tables are missing.
                # This only applies when the revision graph itself is valid and
                # the failure looks like a partially-applied database state.
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
                    retry_started = time.monotonic()
                    migration_retry_ok = run_migrations()
                    phase_timings["run_migrations_retry_ms"] = capture_phase_duration(
                        "preflight.run_migrations_retry",
                        retry_started,
                        print,
                        extra={
                            "boot_id": startup_boot_id,
                            "ok": str(migration_retry_ok).lower(),
                        },
                    )
                    migration_ok = migration_retry_ok
                    if migration_ok:
                        print("[preflight] Migration succeeded on retry")
                except Exception as e:
                    print(f"[preflight] Cleanup/retry failed: {e}")
    else:
        print("[preflight] Skipping migrations since database setup failed")

    # Verify critical tables exist regardless of migration result
    tables_started = time.monotonic()
    tables_ok = verify_critical_tables()
    phase_timings["verify_critical_tables_ms"] = capture_phase_duration(
        "preflight.verify_critical_tables",
        tables_started,
        print,
        extra={"boot_id": startup_boot_id, "ok": str(tables_ok).lower()},
    )

    preflight_total_ms = int((time.monotonic() - preflight_started) * 1000)
    write_preflight_contract(
        {
            "startup_boot_id": startup_boot_id,
            "written_at": time.time(),
            "db_fingerprint": db_fingerprint,
            "db_ok": db_ok,
            "critical_tables_ok": tables_ok,
            "migration_ok": migration_ok,
            "repair_dry_run_ok": repair_dry_run_ok,
            "repair_apply_ok": repair_apply_ok,
            "migration_retry_ok": migration_retry_ok,
            "phase_timings_ms": phase_timings,
            "preflight_total_ms": preflight_total_ms,
        }
    )
    print(
        "[preflight] Wrote startup contract "
        f"(boot_id={startup_boot_id}, total_ms={preflight_total_ms})"
    )

    if not tables_ok:
        print("[preflight] FATAL: Critical tables missing after migration!")
        print("[preflight] The application cannot start without these tables.")
        print("[preflight] Check PostgreSQL connection and Alembic configuration.")
        sys.exit(1)

    print(
        f"[startup-phase] label=preflight.total duration_ms={preflight_total_ms} "
        f"boot_id={startup_boot_id}"
    )
    print("[preflight] Preflight complete, starting application...")
