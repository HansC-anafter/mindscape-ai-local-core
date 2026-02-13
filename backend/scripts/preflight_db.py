#!/usr/bin/env python3
"""
Pre-flight database check: ensures required databases exist before
the main application starts. This runs BEFORE uvicorn imports main.py,
which is necessary because MindscapeStore() is instantiated at module
import time and will crash if the database doesn't exist.
"""
import os
import sys
import time


def ensure_databases():
    """Create missing databases by connecting to the default 'postgres' DB."""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        print("[preflight] psycopg2 not available, skipping DB check")
        return

    pg_host = os.getenv("POSTGRES_CORE_HOST", os.getenv("POSTGRES_HOST", "postgres"))
    pg_port = int(os.getenv("POSTGRES_CORE_PORT", os.getenv("POSTGRES_PORT", "5432")))
    pg_user = os.getenv("POSTGRES_CORE_USER", os.getenv("POSTGRES_USER", "mindscape"))
    pg_pass = os.getenv(
        "POSTGRES_CORE_PASSWORD",
        os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
    )
    core_db = os.getenv("POSTGRES_CORE_DB", "mindscape_core")
    vector_db = os.getenv("POSTGRES_VECTOR_DB", "mindscape_vectors")

    # Retry loop: postgres might still be starting up
    max_retries = 10
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
            return

        except psycopg2.OperationalError as e:
            print(
                f"[preflight] PostgreSQL not ready (attempt {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(min(2 ** (attempt - 1), 10))
            else:
                print("[preflight] WARNING: Could not verify databases after retries")
                print("[preflight] Proceeding anyway - app may fail if DBs missing")

        except Exception as e:
            print(f"[preflight] Unexpected error: {e}")
            return


if __name__ == "__main__":
    ensure_databases()
