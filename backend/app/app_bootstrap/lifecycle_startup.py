import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI

from backend.app.app_bootstrap.knowledge_projection_registry import (
    hydrate_knowledge_projection_registry,
)
from backend.app.app_bootstrap.lifecycle_common import (
    _consume_preflight_contract_decision,
)
from backend.app.app_bootstrap.startup_contract import capture_phase_duration
from backend.app.app_bootstrap.lifecycle_startup_services import (
    ensure_meeting_sessions_table,
    ensure_reasoning_traces_table,
    schedule_compile_job_startup_services,
    schedule_host_resource_rehydrate_task,
    schedule_host_resource_worker_reconcile_task,
    schedule_pending_pack_validation_task,
    start_agent_dispatch_services,
    start_codex_pool_sweeper,
    start_scene_generation_dispatch_services,
    start_zombie_reaper,
)

logger = logging.getLogger(__name__)


def _check_dependency_updates() -> None:
    if os.getenv("ENVIRONMENT") != "development":
        return
    try:
        build_reqs_path = Path("/app/requirements.txt")
        runtime_reqs_path = Path("/app/backend/requirements.txt")

        if build_reqs_path.exists() and runtime_reqs_path.exists():
            build_hash = hashlib.md5(build_reqs_path.read_bytes()).hexdigest()
            runtime_hash = hashlib.md5(runtime_reqs_path.read_bytes()).hexdigest()

            if build_hash != runtime_hash:
                logger.warning("\n" + "!" * 80)
                logger.warning("DEPENDENCY MISMATCH DETECTED!")
                logger.warning(
                    "The requirements.txt in your running container differs from your local code."
                )
                logger.warning(
                    "This means your Docker image is outdated and missing new dependencies."
                )
                logger.warning(
                    "PLEASE RUN THE PLATFORM COMPOSE FACADE WITH: up -d --build"
                )
                logger.warning("!" * 80 + "\n")
        else:
            logger.debug(
                "Could not find both requirements.txt files for dependency check. Skipping."
            )
    except Exception as e:
        logger.warning(f"Dependency check failed: {e}")


def _initialize_cloud_connector(app: FastAPI) -> None:
    cloud_connector_enabled = (
        os.getenv("CLOUD_CONNECTOR_ENABLED", "false").lower() == "true"
    )
    if not cloud_connector_enabled:
        return
    try:
        from backend.app.services.cloud_connector import CloudConnector

        connector = CloudConnector()
        app.state.cloud_connector = connector
        asyncio.create_task(connector.connect())
        logger.info("Cloud Connector initialized and connecting...")
    except Exception as e:
        logger.warning(f"Failed to initialize Cloud Connector: {e}", exc_info=True)


def _initialize_execution_pool(app: FastAPI) -> None:
    try:
        from backend.app.services.execution_pool import ExecutionPoolDispatcher

        app.state.execution_pool = ExecutionPoolDispatcher()
        logger.info("Execution Pool Dispatcher initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Execution Pool: {e}", exc_info=True)


def _ensure_required_databases(
    *,
    preflight_contract_trusted: bool,
    preflight_contract_reason: str,
) -> None:
    db_check_started = time.monotonic()
    if preflight_contract_trusted:
        logger.info(
            "Skipping duplicate database existence verification due to trusted preflight contract"
        )
        capture_phase_duration(
            "startup.db_existence_check_skipped",
            db_check_started,
            logger,
            extra={"reason": preflight_contract_reason},
        )
        return

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
        vector_db = os.getenv("POSTGRES_VECTOR_DB", "mindscape_vectors")

        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_pass,
            dbname="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        for db_name in [core_db, vector_db]:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"Created missing database: {db_name}")

        cur.close()
        conn.close()
        vconn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_pass,
            dbname=vector_db,
        )
        vconn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        vcur = vconn.cursor()
        vcur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        vcur.close()
        vconn.close()
    except Exception as e:
        logger.warning(f"Database auto-creation check failed (non-blocking): {e}")
    finally:
        capture_phase_duration("startup.db_existence_check", db_check_started, logger)


def _verify_default_profile_seed() -> None:
    try:
        from backend.app.services.mindscape_store import MindscapeStore as _MS

        _store = _MS()
        _store.ensure_default_profile()
        logger.info("Default profile seeding verified after migrations")
    except Exception as e:
        logger.warning(f"Post-migration default profile seeding failed: {e}")


def _verify_critical_tables(
    *,
    preflight_contract_trusted: bool,
    preflight_contract_reason: str,
) -> None:
    critical_table_started = time.monotonic()
    if preflight_contract_trusted:
        logger.info(
            "Skipping duplicate critical table verification due to trusted preflight contract"
        )
        capture_phase_duration(
            "startup.critical_table_check_skipped",
            critical_table_started,
            logger,
            extra={"reason": preflight_contract_reason},
        )
        return

    try:
        from sqlalchemy import text

        from app.database.config import get_postgres_url_core
        from app.database.engine_factory import create_transient_transaction_engine

        _verify_db_url = get_postgres_url_core(required=False)
        if _verify_db_url:
            _verify_engine = create_transient_transaction_engine(
                _verify_db_url,
                "local-core-startup-critical-table-check",
            )
            _critical_tables = [
                "profiles",
                "workspaces",
                "system_settings",
                "user_configs",
            ]
            _missing = []
            with _verify_engine.connect() as _conn:
                for _tbl in _critical_tables:
                    _result = _conn.execute(
                        text(
                            "SELECT EXISTS ("
                            "  SELECT 1 FROM information_schema.tables"
                            "  WHERE table_name = :t AND table_schema = 'public'"
                            ")"
                        ),
                        {"t": _tbl},
                    )
                    if not _result.scalar():
                        _missing.append(_tbl)
            _verify_engine.dispose()

            if _missing:
                logger.error("=" * 60)
                logger.error("CRITICAL: Required database tables are missing!")
                logger.error(f"Missing tables: {', '.join(_missing)}")
                logger.error("The API will fail on most requests until this is fixed.")
                logger.error("=" * 60)
            else:
                logger.info(
                    "Critical table verification passed (%d tables)",
                    len(_critical_tables),
                )
    except Exception as e:
        logger.warning(f"Critical table verification failed (non-blocking): {e}")
    finally:
        capture_phase_duration(
            "startup.critical_table_check",
            critical_table_started,
            logger,
        )


async def run_startup(app: FastAPI):
    """Initialize database tables and background tasks on startup."""
    logger.info("Application startup hook entered (pid=%s)", os.getpid())
    startup_started = time.monotonic()
    preflight_contract_trusted, preflight_contract_reason, preflight_contract = (
        _consume_preflight_contract_decision()
    )
    app.state.preflight_contract_trusted = preflight_contract_trusted
    app.state.preflight_contract_reason = preflight_contract_reason
    app.state.preflight_contract = preflight_contract
    app.state.playbook_registry_post_ready_status = "deferred"
    app.state.playbook_registry_post_ready_error = None
    app.state.tool_rag_post_ready_status = "deferred"
    app.state.tool_rag_post_ready_error = None
    app.state.runtime_migrations_post_ready_status = "deferred"
    app.state.runtime_migrations_post_ready_error = None
    logger.info(
        "Preflight contract decision: trusted=%s reason=%s",
        preflight_contract_trusted,
        preflight_contract_reason,
    )

    try:
        from backend.app.routes.core.playbook.handlers import register_playbook_handlers

        await register_playbook_handlers(app)
        logger.info("Playbook handlers registered successfully")
    except Exception as e:
        logger.warning(f"Failed to register playbook handlers: {e}", exc_info=True)

    _check_dependency_updates()
    _initialize_cloud_connector(app)
    _initialize_execution_pool(app)
    hydrate_knowledge_projection_registry(app)
    _ensure_required_databases(
        preflight_contract_trusted=preflight_contract_trusted,
        preflight_contract_reason=preflight_contract_reason,
    )

    logger.info("Capability/runtime migrations deferred to post-ready task")
    migration_started = time.monotonic()
    capture_phase_duration(
        "startup.migration_orchestrator_deferred",
        migration_started,
        logger,
    )

    _verify_default_profile_seed()
    start_zombie_reaper()
    ensure_reasoning_traces_table()
    ensure_meeting_sessions_table()
    schedule_compile_job_startup_services()
    start_scene_generation_dispatch_services()
    logger.info("Tool RAG warm-up deferred to post-ready task")
    _verify_critical_tables(
        preflight_contract_trusted=preflight_contract_trusted,
        preflight_contract_reason=preflight_contract_reason,
    )
    start_agent_dispatch_services()
    schedule_pending_pack_validation_task(app)
    schedule_host_resource_rehydrate_task(app)
    schedule_host_resource_worker_reconcile_task(app)
    start_codex_pool_sweeper(app)
    capture_phase_duration("startup.total", startup_started, logger)
