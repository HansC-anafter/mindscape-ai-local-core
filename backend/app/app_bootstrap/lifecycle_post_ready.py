import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI

from backend.app.app_bootstrap.lifecycle_common import (
    _core_database_accepts_work,
    _env_int,
    _run_post_ready_heavy_work,
    _should_run_post_ready_playbook_registry_warmup,
    _wait_for_post_ready_bind_grace,
)
from backend.app.init_db import init_mindscape_tables
from backend.app.services.tool_rag_refresh import refresh_tool_rag_corpus

logger = logging.getLogger(__name__)


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


async def _run_post_ready_tool_rag_warmup(app: FastAPI) -> None:
    """Warm the shared tool corpus after readiness, not during startup."""
    try:
        await _wait_for_post_ready_bind_grace("tool-rag-post-ready-warmup")
        app.state.tool_rag_post_ready_status = "running"
        app.state.tool_rag_post_ready_error = None
        from backend.app.services.pack_activation_service import PackActivationService
        from backend.app.services.stores.installed_packs_store import InstalledPacksStore

        def _refresh_tool_rag_corpus_in_worker():
            return asyncio.run(
                refresh_tool_rag_corpus(
                    log_prefix="Tool RAG post-ready warm-up",
                    include_playbooks=False,
                    skip_when_index_exists=True,
                )
            )

        tes, indexed_count, mode = await _run_post_ready_heavy_work(
            app,
            "tool-rag-post-ready-warmup",
            _refresh_tool_rag_corpus_in_worker,
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
        app.state.tool_rag_post_ready_status = "completed"
    except asyncio.CancelledError:
        logger.info("Tool RAG post-ready warm-up cancelled")
        app.state.tool_rag_post_ready_status = "cancelled"
        raise
    except Exception as exc:
        app.state.tool_rag_post_ready_completed = False
        app.state.tool_rag_post_ready_status = "failed"
        app.state.tool_rag_post_ready_error = str(exc)
        logger.warning("Tool RAG post-ready warm-up failed: %s", exc, exc_info=True)


async def _run_post_ready_playbook_registry_warmup(app: FastAPI) -> None:
    """Load local capability playbooks after readiness and reconcile activation state."""
    try:
        if not _should_run_post_ready_playbook_registry_warmup():
            app.state.playbook_registry_post_ready_completed = True
            app.state.playbook_registry_post_ready_status = "lazy"
            app.state.playbook_registry_post_ready_error = None
            logger.info("Playbook registry post-ready warm-up uses lazy loading")
            return
        await _wait_for_post_ready_bind_grace(
            "playbook-registry-post-ready-warmup"
        )
        app.state.playbook_registry_post_ready_status = "running"
        app.state.playbook_registry_post_ready_error = None
        from backend.app.services.playbook_registry import get_playbook_registry

        def _load_playbook_registry_in_worker():
            registry = get_playbook_registry()
            registry._load_all_playbooks_sync()
            return registry

        await _run_post_ready_heavy_work(
            app,
            "playbook-registry-post-ready-warmup",
            _load_playbook_registry_in_worker,
        )
        app.state.playbook_registry_post_ready_completed = True
        app.state.playbook_registry_post_ready_status = "completed"
        logger.info("Playbook registry post-ready warm-up completed")
    except asyncio.CancelledError:
        logger.info("Playbook registry post-ready warm-up cancelled")
        app.state.playbook_registry_post_ready_status = "cancelled"
        raise
    except Exception as exc:
        app.state.playbook_registry_post_ready_completed = False
        app.state.playbook_registry_post_ready_status = "failed"
        app.state.playbook_registry_post_ready_error = str(exc)
        logger.warning(
            "Playbook registry post-ready warm-up failed: %s",
            exc,
            exc_info=True,
        )


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


async def _run_post_ready_runtime_migrations(app: FastAPI) -> None:
    """Run capability/runtime migrations after readiness so bind is never blocked."""
    try:
        await _wait_for_post_ready_bind_grace("runtime-migrations-post-ready")
        app.state.runtime_migrations_post_ready_status = "running"
        app.state.runtime_migrations_post_ready_error = None
        from backend.app.services.migrations import MigrationOrchestrator

        app_dir = Path(__file__).parent.parent
        capabilities_root = app_dir / "capabilities"
        alembic_configs = {
            "postgres": app_dir.parent / "alembic.postgres.ini",
        }

        orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)
        logger.info("Post-ready runtime migrations starting")
        postgres_result = await asyncio.to_thread(
            orchestrator.apply,
            "postgres",
            False,
        )
        status = postgres_result.get("status")
        if status == "validation_failed":
            app.state.runtime_migrations_post_ready_status = "validation_failed"
            app.state.runtime_migrations_post_ready_error = str(
                postgres_result.get("failed_checks")
            )
            logger.error(
                "Post-ready PostgreSQL migration validation failed: %s",
                postgres_result.get("failed_checks"),
            )
            await asyncio.to_thread(init_mindscape_tables)
            logger.info("Mindscape tables initialized via init_db.py fallback")
        elif status == "error":
            app.state.runtime_migrations_post_ready_status = "error"
            app.state.runtime_migrations_post_ready_error = str(
                postgres_result.get("error")
            )
            logger.error(
                "Post-ready PostgreSQL migration error: %s",
                postgres_result.get("error"),
            )
            await asyncio.to_thread(init_mindscape_tables)
            logger.info("Mindscape tables initialized via init_db.py fallback")
        else:
            app.state.runtime_migrations_post_ready_status = status or "completed"
            if status not in {"completed", "up_to_date"}:
                detail = (
                    postgres_result.get("error")
                    or postgres_result.get("failed_checks")
                    or postgres_result
                )
                app.state.runtime_migrations_post_ready_error = str(detail)
                logger.warning(
                    "Post-ready PostgreSQL migrations returned non-success status=%s detail=%s",
                    status,
                    detail,
                )
            logger.info(
                "Post-ready PostgreSQL migrations: %s, applied: %s",
                status,
                postgres_result.get("migrations_applied", 0),
            )
        app.state.runtime_migrations_post_ready_completed = True
    except asyncio.CancelledError:
        logger.info("Post-ready runtime migrations task cancelled")
        app.state.runtime_migrations_post_ready_status = "cancelled"
        raise
    except Exception as exc:
        app.state.runtime_migrations_post_ready_completed = False
        app.state.runtime_migrations_post_ready_status = "failed"
        app.state.runtime_migrations_post_ready_error = str(exc)
        logger.warning(
            "Post-ready runtime migrations failed: %s",
            exc,
            exc_info=True,
        )


async def _run_object_index_sync_loop(app: FastAPI) -> None:
    """Run AOL concrete object index discovery after readiness, then periodically."""
    from backend.app.services.object_index_sync_service import (
        get_object_index_sync_service,
        get_object_index_sync_status,
    )

    startup_delay = _env_int(
        "AOL_OBJECT_INDEX_SYNC_STARTUP_DELAY_SECONDS",
        3,
        minimum=0,
        maximum=300,
    )
    interval_seconds = _env_int(
        "AOL_OBJECT_INDEX_SYNC_INTERVAL_SECONDS",
        300,
        minimum=0,
        maximum=86400,
    )
    workspace_limit = _env_int(
        "AOL_OBJECT_INDEX_SYNC_WORKSPACE_LIMIT",
        50,
        minimum=1,
        maximum=250,
    )
    per_workspace_limit = _env_int(
        "AOL_OBJECT_INDEX_SYNC_PER_WORKSPACE_LIMIT",
        100,
        minimum=1,
        maximum=500,
    )
    service = get_object_index_sync_service()
    tracker = get_object_index_sync_status()

    if startup_delay:
        await asyncio.sleep(startup_delay)
    iteration = 0
    while True:
        reason = (
            "post_ready_object_index_sync"
            if iteration == 0
            else "scheduled_object_index_sync"
        )
        try:
            db_ready, db_error = _core_database_accepts_work()
            if not db_ready:
                app.state.object_index_sync_status = "deferred"
                app.state.object_index_sync_error = db_error
                logger.warning("AOL object index sync deferred: %s", db_error)
                iteration += 1
                if interval_seconds <= 0:
                    break
                await asyncio.sleep(interval_seconds)
                continue

            app.state.object_index_sync_status = "running"
            app.state.object_index_sync_error = None
            summary = await service.sync_recent_workspaces(
                workspace_limit=workspace_limit,
                per_workspace_limit=per_workspace_limit,
                reason=reason,
            )
            app.state.object_index_sync_status = tracker.state
            app.state.object_index_sync_error = tracker.last_error
            app.state.object_index_sync_last_summary = summary
            logger.info(
                "AOL object index sync completed: reason=%s workspaces=%d indexed=%d",
                reason,
                summary.get("workspace_count", 0),
                summary.get("indexed_count", 0),
            )
        except asyncio.CancelledError:
            app.state.object_index_sync_status = "cancelled"
            logger.info("AOL object index sync task cancelled")
            raise
        except Exception as exc:
            app.state.object_index_sync_status = "failed"
            app.state.object_index_sync_error = str(exc)
            logger.warning(
                "AOL object index sync failed: %s",
                exc,
                exc_info=True,
            )

        iteration += 1
        if interval_seconds <= 0:
            break
        await asyncio.sleep(interval_seconds)


async def _rehydrate_host_resource_projection_post_ready() -> None:
    """Rebuild Redis hot projection from durable ledger after readiness."""
    try:
        await asyncio.sleep(0)
        from backend.app.services.host_resources.manager import (
            rehydrate_route_reservation_projection,
        )

        reservations = await asyncio.to_thread(
            rehydrate_route_reservation_projection
        )
        logger.info(
            "Host resource reservation projection rehydrated: active=%d",
            len(reservations),
        )
    except Exception as exc:
        logger.warning(
            "Host resource reservation projection rehydrate failed (non-blocking): %s",
            exc,
        )
