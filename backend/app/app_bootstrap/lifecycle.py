import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.app.app_bootstrap.startup_contract import (
    capture_phase_duration,
    compute_db_fingerprint,
    delete_preflight_contract,
    is_contract_trustworthy,
    read_preflight_contract,
)
from backend.app.init_db import init_mindscape_tables
from backend.app.services.tool_rag_refresh import refresh_tool_rag_corpus

logger = logging.getLogger(__name__)
_TOOL_RAG_POST_READY_TASK_ATTR = "_tool_rag_post_ready_task"
_PACK_VALIDATION_RESUME_TASK_ATTR = "_pack_validation_resume_task"


async def _sync_tool_rag_pack_embedding_state(
    *,
    tool_embedding_service,
    activation_service,
    installed_packs_store,
):
    """Reconcile pack embedding state without blocking the main event loop."""
    synced = 0
    pack_ids = await asyncio.to_thread(installed_packs_store.list_installed_pack_ids)
    for pack_id in pack_ids:
        try:
            stats = await tool_embedding_service.get_capability_embedding_status(pack_id)
            await asyncio.to_thread(
                activation_service.record_embedding_observed,
                pack_id=pack_id,
                row_count=stats["row_count"],
                latest_updated_at=stats["latest_updated_at"],
            )
            synced += 1
        except Exception as sync_exc:
            logger.warning(
                "Tool RAG pack embedding state sync failed for %s: %s",
                pack_id,
                sync_exc,
            )
        await asyncio.sleep(0)
    logger.info(
        "Tool RAG pack embedding state sync completed: %d packs checked.",
        synced,
    )


def _consume_preflight_contract_decision() -> tuple[bool, str, dict]:
    contract = read_preflight_contract() or {}
    try:
        trusted, reason = is_contract_trustworthy(
            contract,
            current_db_fingerprint=compute_db_fingerprint(),
        )
    except Exception as exc:
        trusted, reason = False, f"fingerprint_error:{exc}"
    finally:
        delete_preflight_contract()
    return trusted, reason, contract


async def _run_post_ready_tool_rag_warmup(app: FastAPI) -> None:
    """Warm the shared tool corpus after readiness, not during startup."""
    try:
        from backend.app.services.pack_activation_service import PackActivationService
        from backend.app.services.stores.installed_packs_store import InstalledPacksStore

        await asyncio.sleep(0)
        tes, indexed_count, mode = await refresh_tool_rag_corpus(
            log_prefix="Tool RAG post-ready warm-up"
        )
        logger.info(
            "Tool RAG post-ready warm-up completed: indexed=%d mode=%s",
            indexed_count,
            mode,
        )
        await _sync_tool_rag_pack_embedding_state(
            tool_embedding_service=tes,
            activation_service=PackActivationService(),
            installed_packs_store=InstalledPacksStore(),
        )
        app.state.tool_rag_post_ready_completed = True
    except asyncio.CancelledError:
        logger.info("Tool RAG post-ready warm-up cancelled")
        raise
    except Exception as exc:
        app.state.tool_rag_post_ready_completed = False
        logger.warning("Tool RAG post-ready warm-up failed: %s", exc, exc_info=True)


async def _resume_pending_pack_validations_post_ready() -> None:
    """Resume pending pack validations without blocking API bind/startup."""
    try:
        from backend.app.services.pack_validation_background import (
            resume_pending_pack_validations,
        )

        await asyncio.sleep(0)
        await resume_pending_pack_validations()
        logger.info("Pending pack validations resume task completed")
    except asyncio.CancelledError:
        logger.info("Pending pack validations resume task cancelled")
        raise
    except Exception as exc:
        logger.warning(
            "Pending pack validations resume task failed: %s",
            exc,
            exc_info=True,
        )


async def _run_compile_job_startup_recovery() -> None:
    """Resume/reconcile orphaned compile jobs without blocking API startup."""
    try:
        from backend.app.services.compile_job_reconciler import CompileJobReconciler
        from backend.app.services.stores.compile_job_store import CompileJobStore
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
        )

        # Yield once so uvicorn can finish startup and begin serving health checks.
        await asyncio.sleep(0)
        reconcile_summary = await CompileJobReconciler(
            compile_job_store=CompileJobStore(),
            meeting_session_store=MeetingSessionStore(),
        ).recover_startup_orphans(limit=500)
        logger.info(
            "Compile job startup reconcile complete: inspected=%d resumed=%d succeeded=%d failed=%d session_failed=%d skipped=%d",
            reconcile_summary["inspected"],
            reconcile_summary["resumed"],
            reconcile_summary["succeeded"],
            reconcile_summary["failed"],
            reconcile_summary["session_failed"],
            reconcile_summary["skipped"],
        )
    except Exception as e:
        logger.warning(
            "Compile job startup recovery failed (non-blocking): %s",
            e,
            exc_info=True,
        )


async def _start_compile_job_startup_services() -> None:
    """Start compile-job background services after API startup can complete."""
    try:
        from backend.app.services.compile_job_dispatch_manager import (
            get_compile_job_dispatch_manager,
        )

        await asyncio.sleep(0)
        get_compile_job_dispatch_manager().start_background_services()
        logger.info("Compile job dispatch background services started")
        await _run_compile_job_startup_recovery()
    except Exception as e:
        logger.warning(
            "Compile job startup services failed (non-blocking): %s",
            e,
            exc_info=True,
        )

async def run_startup(app: FastAPI):
    """Initialize database tables and background tasks on startup"""
    logger.info("Application startup hook entered (pid=%s)", os.getpid())
    startup_started = time.monotonic()
    preflight_contract_trusted, preflight_contract_reason, preflight_contract = (
        _consume_preflight_contract_decision()
    )
    app.state.preflight_contract_trusted = preflight_contract_trusted
    app.state.preflight_contract_reason = preflight_contract_reason
    app.state.preflight_contract = preflight_contract
    logger.info(
        "Preflight contract decision: trusted=%s reason=%s",
        preflight_contract_trusted,
        preflight_contract_reason,
    )

    # Register playbook handlers
    try:
        from backend.app.routes.core.playbook.handlers import register_playbook_handlers

        await register_playbook_handlers(app)
        logger.info("Playbook handlers registered successfully")
    except Exception as e:
        logger.warning(f"Failed to register playbook handlers: {e}", exc_info=True)

    # Check for dependency updates (Development Mode only)
    # Compares build-time requirements (in image) vs run-time requirements (volume mounted code)
    if os.getenv("ENVIRONMENT") == "development":
        try:
            from pathlib import Path
            import hashlib

            # Paths inside container based on Dockerfile structure
            # /app/requirements.txt is COPY'd during build (frozen state)
            # /app/backend/requirements.txt is volume mounted from host (current state)
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
                    logger.warning("PLEASE RUN: docker compose up --build")
                    logger.warning("!" * 80 + "\n")
            else:
                logger.debug(
                    "Could not find both requirements.txt files for dependency check. Skipping."
                )
        except Exception as e:
            logger.warning(f"Dependency check failed: {e}")

    # Initialize Cloud Connector (if enabled)
    cloud_connector_enabled = (
        os.getenv("CLOUD_CONNECTOR_ENABLED", "false").lower() == "true"
    )
    if cloud_connector_enabled:
        try:
            import asyncio
            from backend.app.services.cloud_connector import CloudConnector

            connector = CloudConnector()
            app.state.cloud_connector = connector
            asyncio.create_task(connector.connect())
            logger.info("Cloud Connector initialized and connecting...")
        except Exception as e:
            logger.warning(f"Failed to initialize Cloud Connector: {e}", exc_info=True)

    # Initialize Execution Pool Dispatcher (always available)
    try:
        from backend.app.services.execution_pool import ExecutionPoolDispatcher

        app.state.execution_pool = ExecutionPoolDispatcher()
        logger.info("Execution Pool Dispatcher initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Execution Pool: {e}", exc_info=True)

    # Ensure required databases exist unless the same boot already verified them.
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
    else:
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

            # Connect to default 'postgres' database to create missing databases
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

            # Ensure pgvector extension exists in vector database
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

    # Run database migrations using unified migration orchestrator
    logger.info("Running database migrations...")
    migration_started = time.monotonic()
    try:
        from pathlib import Path
        from backend.app.services.migrations import MigrationOrchestrator

        # Get path referencing the root backend/app/capabilities directory where packs stay
        app_dir = Path(__file__).parent.parent
        capabilities_root = app_dir / "capabilities"
        alembic_configs = {
            "postgres": app_dir.parent / "alembic.postgres.ini",
        }

        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

        # Run PostgreSQL migrations
        logger.info("Checking PostgreSQL migrations...")
        postgres_result = orchestrator.apply("postgres", dry_run=False)
        if postgres_result.get("status") == "validation_failed":
            logger.error(
                f"PostgreSQL migration validation failed: {postgres_result.get('failed_checks')}"
            )
            logger.warning("Falling back to init_db.py for PostgreSQL tables...")
            try:
                init_mindscape_tables()
                logger.info("Mindscape tables initialized via init_db.py fallback")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize mindscape tables via init_db.py: {e}"
                )
        elif postgres_result.get("status") == "error":
            logger.error(f"PostgreSQL migration error: {postgres_result.get('error')}")
            logger.warning("Falling back to init_db.py for PostgreSQL tables...")
            try:
                init_mindscape_tables()
                logger.info("Mindscape tables initialized via init_db.py fallback")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize mindscape tables via init_db.py: {e}"
                )
        else:
            logger.info(
                f"PostgreSQL migrations: {postgres_result.get('status')}, applied: {postgres_result.get('migrations_applied', 0)}"
            )
            logger.info("Database migrations completed via unified migration system")
    except ImportError as e:
        logger.warning(f"Migration orchestrator not available: {e}")
        logger.warning("Falling back to init_db.py...")
        try:
            init_mindscape_tables()
            logger.info("Mindscape tables initialized via init_db.py fallback")
        except Exception as e:
            logger.warning(
                f"Failed to initialize mindscape tables (will retry on first use): {e}"
            )
    except Exception as e:
        logger.error(f"Migration system error: {e}", exc_info=True)
        logger.warning("Falling back to init_db.py...")
        try:
            init_mindscape_tables()
            logger.info("Mindscape tables initialized via init_db.py fallback")
        except Exception as e2:
            logger.warning(
                f"Failed to initialize mindscape tables (will retry on first use): {e2}"
            )
    finally:
        capture_phase_duration("startup.migration_orchestrator", migration_started, logger)

    # Re-run ensure_default_profile after migrations complete.
    try:
        from backend.app.services.mindscape_store import MindscapeStore as _MS
        _store = _MS()
        _store.ensure_default_profile()
        logger.info("Default profile seeding verified after migrations")
    except Exception as e:
        logger.warning(f"Post-migration default profile seeding failed: {e}")

    # Reap zombie tasks on startup and start periodic background reaper
    try:
        from backend.app.services.stores.tasks_store import TasksStore as _ReaperStore
        import asyncio

        _reaper_store = _ReaperStore()
        reaped = _reaper_store.reap_zombie_tasks()
        if reaped:
            logger.info(
                "Startup zombie reaper: cleaned %d zombie tasks: %s",
                len(reaped),
                reaped[:5],
            )

        async def _zombie_reaper_loop():
            while True:
                await asyncio.sleep(300)  # 5 minutes
                try:
                    store = _ReaperStore()
                    store.reap_zombie_tasks()
                except Exception as exc:
                    logger.warning("Periodic zombie reaper error: %s", exc)

        asyncio.create_task(_zombie_reaper_loop())
        logger.info("Zombie task reaper started (interval: 5 minutes)")
    except Exception as e:
        logger.warning(f"Failed to start zombie task reaper: {e}", exc_info=True)

    # Verify critical tables exist
    try:
        from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

        _rt_store = ReasoningTracesStore()
        _rt_store.ensure_table()
        logger.info("reasoning_traces table ensured (startup)")
    except Exception as e:
        logger.warning(f"Reasoning traces table bootstrap failed (non-blocking): {e}")

    try:
        from backend.app.services.stores.meeting_session_store import MeetingSessionStore

        _ms_store = MeetingSessionStore()
        logger.info("meeting_sessions table ensured (startup)")
    except Exception as e:
        logger.warning(f"Meeting session table bootstrap failed (non-blocking): {e}")

    try:
        from backend.app.services.stores.compile_job_store import CompileJobStore

        _compile_job_store = CompileJobStore()
        logger.info("compile_jobs table ensured (startup)")

        asyncio.create_task(_start_compile_job_startup_services())
        logger.info("Compile job startup services task scheduled")
    except Exception as e:
        logger.warning(
            f"Compile job startup reconcile failed (non-blocking): {e}",
            exc_info=True,
        )

    try:
        from backend.app.capabilities.performance_direction.services.scene_generation_dispatch_manager import (
            get_scene_generation_dispatch_manager,
        )
        from backend.app.services.stores.installed_packs_store import (
            InstalledPacksStore,
        )

        if "performance_direction" in set(
            InstalledPacksStore().list_enabled_pack_ids()
        ):
            started = (
                get_scene_generation_dispatch_manager().start_background_services()
            )
            if started:
                logger.info("Scene generation dispatch background services started")
            else:
                logger.info(
                    "Scene generation dispatch startup skipped: scene_generation_jobs schema unavailable"
                )
        else:
            logger.info(
                "Scene generation dispatch startup skipped: performance_direction not enabled"
            )
    except Exception as e:
        logger.warning(
            f"Scene generation dispatch startup failed (non-blocking): {e}",
            exc_info=True,
        )

    logger.info("Tool RAG warm-up deferred to post-ready task")

    # Check database core tables unless the same boot already verified them.
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
    else:
        try:
            from sqlalchemy import text, create_engine

            _verify_db_url = os.environ.get("DATABASE_URL_CORE") or os.environ.get(
                "DATABASE_URL"
            )
            if _verify_db_url:
                _verify_engine = create_engine(_verify_db_url)
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

    # Start agent dispatch background services
    try:
        from backend.app.routes.agent_dispatch import get_agent_dispatch_manager

        get_agent_dispatch_manager().start_background_services()
        logger.info("Agent dispatch background services started")
    except Exception as e:
        logger.warning(
            f"Failed to start agent dispatch background services: {e}",
            exc_info=True,
        )

    try:
        pending_pack_validation_task = asyncio.create_task(
            _resume_pending_pack_validations_post_ready(),
            name="pending-pack-validations-resume",
        )
        setattr(
            app.state,
            _PACK_VALIDATION_RESUME_TASK_ATTR,
            pending_pack_validation_task,
        )
        logger.info("Pending pack validations resume task scheduled")
    except Exception as e:
        logger.warning(f"Failed to schedule pending pack validations resume task: {e}")

    capture_phase_duration("startup.total", startup_started, logger)

async def run_shutdown(app: FastAPI):
    """Cleanup on shutdown"""
    logger.warning("Application shutdown hook entered (pid=%s)", os.getpid())
    tool_rag_task = getattr(app.state, _TOOL_RAG_POST_READY_TASK_ATTR, None)
    if tool_rag_task is not None and not tool_rag_task.done():
        tool_rag_task.cancel()
        try:
            await tool_rag_task
        except asyncio.CancelledError:
            logger.info("Tool RAG post-ready warm-up task cancelled during shutdown")
        except Exception as exc:
            logger.warning("Tool RAG post-ready task shutdown wait failed: %s", exc)

    pack_validation_task = getattr(app.state, _PACK_VALIDATION_RESUME_TASK_ATTR, None)
    if pack_validation_task is not None and not pack_validation_task.done():
        pack_validation_task.cancel()
        try:
            await pack_validation_task
        except asyncio.CancelledError:
            logger.info("Pending pack validations resume task cancelled during shutdown")
        except Exception as exc:
            logger.warning(
                "Pending pack validations resume task shutdown wait failed: %s",
                exc,
            )

    if hasattr(app.state, "cloud_connector"):
        connector = app.state.cloud_connector
        if connector:
            try:
                await connector.disconnect()
                logger.info("Cloud Connector disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting Cloud Connector: {e}")

    try:
        from backend.app.services.compile_job_dispatch_manager import (
            get_compile_job_dispatch_manager,
        )
        from backend.app.services.compile_job_reconciler import CompileJobReconciler
        from backend.app.services.compile_job_task_registry import (
            compile_job_task_registry,
        )
        from backend.app.services.stores.compile_job_store import CompileJobStore
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
        )

        get_compile_job_dispatch_manager().stop_background_services()
        logger.info("Compile job dispatch background services stopped")

        in_flight_job_ids = [
            item.job_id
            for item in compile_job_task_registry.snapshot()
        ]
        shutdown_summary = CompileJobReconciler(
            compile_job_store=CompileJobStore(),
            meeting_session_store=MeetingSessionStore(),
        ).requeue_running_jobs_for_shutdown(job_ids=in_flight_job_ids)
        logger.info(
            "Compile job graceful-shutdown requeue complete: inspected=%d requeued=%d session_reset=%d skipped=%d",
            shutdown_summary["inspected"],
            shutdown_summary["requeued"],
            shutdown_summary["session_reset"],
            shutdown_summary["skipped"],
        )
        for job_id in in_flight_job_ids:
            compile_job_task_registry.cancel(job_id)
            compile_job_task_registry.unregister(job_id)
    except Exception as e:
        logger.warning(
            f"Error stopping compile job dispatch background services: {e}",
            exc_info=True,
        )

    try:
        from backend.app.capabilities.performance_direction.services.scene_generation_dispatch_manager import (
            get_scene_generation_dispatch_manager,
        )

        get_scene_generation_dispatch_manager().stop_background_services()
        logger.info("Scene generation dispatch background services stopped")
    except Exception as e:
        logger.warning(
            f"Error stopping scene generation dispatch background services: {e}",
            exc_info=True,
        )

    try:
        from backend.app.routes.agent_dispatch import get_agent_dispatch_manager

        get_agent_dispatch_manager().stop_background_services()
        logger.info("Agent dispatch background services stopped")
    except Exception as e:
        logger.warning(
            f"Error stopping agent dispatch background services: {e}",
            exc_info=True,
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle startup and shutdown hooks."""
    await run_startup(app)
    tool_rag_task = asyncio.create_task(
        _run_post_ready_tool_rag_warmup(app),
        name="tool-rag-post-ready-warmup",
    )
    setattr(app.state, _TOOL_RAG_POST_READY_TASK_ATTR, tool_rag_task)
    logger.info("Tool RAG post-ready warm-up task scheduled")
    try:
        yield
    finally:
        await run_shutdown(app)
