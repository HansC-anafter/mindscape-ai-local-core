import asyncio
import logging
import os

from fastapi import FastAPI

from backend.app.app_bootstrap.lifecycle_common import (
    _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR,
    _CODEX_POOL_SWEEPER_SERVICE_ATTR,
    _HOST_RESOURCE_REHYDRATE_TASK_ATTR,
    _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR,
    _OBJECT_INDEX_SYNC_TASK_ATTR,
    _PACK_VALIDATION_RESUME_TASK_ATTR,
    _PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR,
    _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR,
    _TOOL_RAG_POST_READY_TASK_ATTR,
)

logger = logging.getLogger(__name__)


async def _cancel_task_if_running(task, *, cancelled_log: str, failed_log: str) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info(cancelled_log)
    except Exception as exc:
        logger.warning(failed_log, exc)


async def _cancel_pre_requeue_lifecycle_tasks(app: FastAPI) -> None:
    await _cancel_task_if_running(
        getattr(app.state, _PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR, None),
        cancelled_log="Playbook registry post-ready warm-up task cancelled during shutdown",
        failed_log="Playbook registry post-ready task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _TOOL_RAG_POST_READY_TASK_ATTR, None),
        cancelled_log="Tool RAG post-ready warm-up task cancelled during shutdown",
        failed_log="Tool RAG post-ready task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _PACK_VALIDATION_RESUME_TASK_ATTR, None),
        cancelled_log="Pending pack validations resume task cancelled during shutdown",
        failed_log="Pending pack validations resume task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR, None),
        cancelled_log="Post-ready runtime migrations task cancelled during shutdown",
        failed_log="Post-ready runtime migrations task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _OBJECT_INDEX_SYNC_TASK_ATTR, None),
        cancelled_log="AOL object index sync task cancelled during shutdown",
        failed_log="AOL object index sync task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR, None),
        cancelled_log="Capability install job worker task cancelled during shutdown",
        failed_log="Capability install job worker shutdown wait failed: %s",
    )


async def _cancel_host_resource_lifecycle_tasks(app: FastAPI) -> None:
    await _cancel_task_if_running(
        getattr(app.state, _HOST_RESOURCE_REHYDRATE_TASK_ATTR, None),
        cancelled_log="Host resource rehydrate task cancelled during shutdown",
        failed_log="Host resource rehydrate task shutdown wait failed: %s",
    )
    await _cancel_task_if_running(
        getattr(app.state, _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR, None),
        cancelled_log="Host resource worker target reconcile task cancelled during shutdown",
        failed_log="Host resource worker target reconcile shutdown wait failed: %s",
    )


def _requeue_capability_install_jobs() -> None:
    try:
        from backend.app.services.stores.capability_install_job_store import (
            CapabilityInstallJobStore,
        )

        requeued = CapabilityInstallJobStore().requeue_running_jobs_for_shutdown()
        if requeued:
            logger.info(
                "Capability install graceful-shutdown requeued %d running job(s)",
                requeued,
            )
    except Exception as exc:
        logger.warning(
            "Capability install graceful-shutdown requeue failed: %s",
            exc,
            exc_info=True,
        )


async def _stop_codex_pool_sweeper(app: FastAPI) -> None:
    codex_pool_sweeper = getattr(
        app.state,
        _CODEX_POOL_SWEEPER_SERVICE_ATTR,
        None,
    )
    if codex_pool_sweeper is None:
        return
    codex_pool_sweeper.stop_background_services()
    try:
        await codex_pool_sweeper.wait_closed()
        logger.info("Codex pool sweeper background service stopped")
    except Exception as exc:
        logger.warning(
            "Codex pool sweeper shutdown wait failed: %s",
            exc,
        )


async def _disconnect_cloud_connector(app: FastAPI) -> None:
    if not hasattr(app.state, "cloud_connector"):
        return
    connector = app.state.cloud_connector
    if not connector:
        return
    try:
        await connector.disconnect()
        logger.info("Cloud Connector disconnected")
    except Exception as e:
        logger.warning(f"Error disconnecting Cloud Connector: {e}")


def _stop_compile_job_services() -> None:
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


def _stop_scene_generation_dispatch_services() -> None:
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


def _stop_agent_dispatch_services() -> None:
    try:
        from backend.app.routes.agent_dispatch import get_agent_dispatch_manager

        get_agent_dispatch_manager().stop_background_services()
        logger.info("Agent dispatch background services stopped")
    except Exception as e:
        logger.warning(
            f"Error stopping agent dispatch background services: {e}",
            exc_info=True,
        )


async def run_shutdown(app: FastAPI):
    """Cleanup on shutdown."""
    logger.warning("Application shutdown hook entered (pid=%s)", os.getpid())
    await _cancel_pre_requeue_lifecycle_tasks(app)
    _requeue_capability_install_jobs()
    await _cancel_host_resource_lifecycle_tasks(app)
    await _stop_codex_pool_sweeper(app)
    await _disconnect_cloud_connector(app)
    _stop_compile_job_services()
    _stop_scene_generation_dispatch_services()
    _stop_agent_dispatch_services()
