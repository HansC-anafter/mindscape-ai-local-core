import asyncio
import logging

from fastapi import FastAPI

from backend.app.app_bootstrap.lifecycle_common import (
    _CODEX_POOL_SWEEPER_SERVICE_ATTR,
    _HOST_RESOURCE_REHYDRATE_TASK_ATTR,
    _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR,
    _PACK_VALIDATION_RESUME_TASK_ATTR,
)
from backend.app.app_bootstrap.lifecycle_post_ready import (
    _rehydrate_host_resource_projection_post_ready,
    _resume_pending_pack_validations_post_ready,
)
from backend.app.core.backend_runtime_mode import is_execution_plane

logger = logging.getLogger(__name__)


async def _run_compile_job_startup_recovery() -> None:
    """Resume/reconcile orphaned compile jobs without blocking API startup."""
    try:
        from backend.app.services.compile_job_reconciler import CompileJobReconciler
        from backend.app.services.stores.compile_job_store import CompileJobStore
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
        )

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


def start_zombie_reaper() -> None:
    try:
        from backend.app.services.task_zombie_reaper import (
            reap_zombie_tasks_with_resource_cleanup,
        )

        async def _zombie_reaper_loop():
            try:
                result = await reap_zombie_tasks_with_resource_cleanup()
                if result.task_ids:
                    logger.info(
                        "Startup zombie reaper: cleaned %d zombie tasks: %s "
                        "resource_cleanup_complete=%s",
                        len(result.task_ids),
                        list(result.task_ids[:5]),
                        result.cleanup_complete,
                    )
            except Exception as exc:
                logger.warning("Startup zombie reaper error: %s", exc)
            while True:
                await asyncio.sleep(300)
                try:
                    result = await reap_zombie_tasks_with_resource_cleanup()
                    if result.task_ids:
                        logger.info(
                            "Periodic zombie reaper: cleaned %d zombie tasks "
                            "resource_cleanup_complete=%s",
                            len(result.task_ids),
                            result.cleanup_complete,
                        )
                except Exception as exc:
                    logger.warning("Periodic zombie reaper error: %s", exc)

        asyncio.create_task(_zombie_reaper_loop())
        logger.info("Zombie task reaper started (interval: 5 minutes)")
    except Exception as e:
        logger.warning(f"Failed to start zombie task reaper: {e}", exc_info=True)


def ensure_reasoning_traces_table() -> None:
    try:
        from backend.app.services.stores.reasoning_traces_store import (
            ReasoningTracesStore,
        )

        _rt_store = ReasoningTracesStore()
        _rt_store.ensure_table()
        logger.info("reasoning_traces table ensured (startup)")
    except Exception as e:
        logger.warning(f"Reasoning traces table bootstrap failed (non-blocking): {e}")


def ensure_meeting_sessions_table() -> None:
    try:
        from backend.app.services.stores.meeting_session_store import MeetingSessionStore

        _ms_store = MeetingSessionStore()
        logger.info("meeting_sessions table ensured (startup)")
    except Exception as e:
        logger.warning(f"Meeting session table bootstrap failed (non-blocking): {e}")


def schedule_compile_job_startup_services() -> None:
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


def start_scene_generation_dispatch_services() -> None:
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


def start_agent_dispatch_services() -> None:
    try:
        from backend.app.routes.agent_dispatch import get_agent_dispatch_manager

        get_agent_dispatch_manager().start_background_services()
        logger.info("Agent dispatch background services started")
    except Exception as e:
        logger.warning(
            f"Failed to start agent dispatch background services: {e}",
            exc_info=True,
        )


def schedule_pending_pack_validation_task(app: FastAPI) -> None:
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


def schedule_host_resource_rehydrate_task(app: FastAPI) -> None:
    try:
        host_resource_rehydrate_task = asyncio.create_task(
            _rehydrate_host_resource_projection_post_ready(),
            name="host-resource-reservation-rehydrate",
        )
        setattr(
            app.state,
            _HOST_RESOURCE_REHYDRATE_TASK_ATTR,
            host_resource_rehydrate_task,
        )
        logger.info("Host resource reservation projection rehydrate task scheduled")
    except Exception as e:
        logger.warning(
            "Failed to schedule host resource reservation projection rehydrate: %s",
            e,
        )


def schedule_host_resource_worker_reconcile_task(app: FastAPI) -> None:
    if is_execution_plane():
        try:
            from backend.app.services.host_resources.worker_target_reconciler import (
                run_worker_target_reconcile_loop,
            )

            host_resource_worker_reconcile_task = asyncio.create_task(
                run_worker_target_reconcile_loop(),
                name="host-resource-worker-target-reconcile",
            )
            setattr(
                app.state,
                _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR,
                host_resource_worker_reconcile_task,
            )
            logger.info("Host resource worker target reconcile task scheduled")
        except Exception as e:
            logger.warning(
                "Failed to schedule host resource worker target reconcile task: %s",
                e,
                exc_info=True,
            )
    else:
        setattr(app.state, _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR, None)


def start_codex_pool_sweeper(app: FastAPI) -> None:
    try:
        from backend.app.services.codex_pool_sweeper_service import (
            get_codex_pool_sweeper_service,
        )

        codex_pool_sweeper = get_codex_pool_sweeper_service()
        setattr(app.state, _CODEX_POOL_SWEEPER_SERVICE_ATTR, codex_pool_sweeper)
        started = codex_pool_sweeper.start_background_services()
        logger.info(
            "Codex pool sweeper background service %s",
            "started" if started else "skipped",
        )
    except Exception as e:
        logger.warning(
            f"Failed to start Codex pool sweeper background service: {e}",
            exc_info=True,
        )
