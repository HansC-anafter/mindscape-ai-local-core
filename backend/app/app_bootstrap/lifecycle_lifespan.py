import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.app_bootstrap.lifecycle_common import (
    _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR,
    _OBJECT_INDEX_SYNC_TASK_ATTR,
    _PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR,
    _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR,
    _TOOL_RAG_POST_READY_TASK_ATTR,
    should_run_object_index_sync,
)
from backend.app.app_bootstrap.lifecycle_post_ready import (
    _run_object_index_sync_loop,
    _run_post_ready_playbook_registry_warmup,
    _run_post_ready_runtime_migrations,
    _run_post_ready_tool_rag_warmup,
)
from backend.app.app_bootstrap.lifecycle_shutdown import run_shutdown
from backend.app.app_bootstrap.lifecycle_startup import run_startup
from backend.app.core.backend_runtime_mode import (
    is_execution_plane,
    should_run_post_ready_runtime_migrations,
    should_run_post_ready_tool_rag_warmup,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle startup and shutdown hooks."""
    await run_startup(app)
    playbook_registry_task = asyncio.create_task(
        _run_post_ready_playbook_registry_warmup(app),
        name="playbook-registry-post-ready-warmup",
    )
    setattr(
        app.state,
        _PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR,
        playbook_registry_task,
    )
    logger.info("Playbook registry post-ready warm-up task scheduled")
    if should_run_post_ready_tool_rag_warmup():
        tool_rag_task = asyncio.create_task(
            _run_post_ready_tool_rag_warmup(app),
            name="tool-rag-post-ready-warmup",
        )
        setattr(app.state, _TOOL_RAG_POST_READY_TASK_ATTR, tool_rag_task)
        logger.info("Tool RAG post-ready warm-up task scheduled")
    else:
        setattr(app.state, _TOOL_RAG_POST_READY_TASK_ATTR, None)
        app.state.tool_rag_post_ready_status = "disabled_by_runtime_policy"
        logger.info("Tool RAG post-ready warm-up disabled by runtime policy")
    if should_run_post_ready_runtime_migrations():
        runtime_migrations_task = asyncio.create_task(
            _run_post_ready_runtime_migrations(app),
            name="runtime-migrations-post-ready",
        )
        setattr(
            app.state,
            _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR,
            runtime_migrations_task,
        )
        logger.info("Post-ready runtime migrations task scheduled")
    else:
        setattr(app.state, _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR, None)
        app.state.runtime_migrations_post_ready_status = "disabled_by_runtime_policy"
        logger.info("Post-ready runtime migrations disabled by runtime policy")
    if should_run_object_index_sync():
        object_index_sync_task = asyncio.create_task(
            _run_object_index_sync_loop(app),
            name="aol-object-index-sync",
        )
        setattr(app.state, _OBJECT_INDEX_SYNC_TASK_ATTR, object_index_sync_task)
        app.state.object_index_sync_status = "scheduled"
        app.state.object_index_sync_error = None
        logger.info("AOL object index sync task scheduled")
    else:
        setattr(app.state, _OBJECT_INDEX_SYNC_TASK_ATTR, None)
        app.state.object_index_sync_status = "disabled_by_runtime_policy"
        app.state.object_index_sync_error = None
        try:
            from backend.app.services.object_index_sync_service import (
                get_object_index_sync_status,
            )

            get_object_index_sync_status().mark_disabled("disabled_by_runtime_policy")
        except Exception:
            logger.debug("Failed to mark AOL object index sync disabled", exc_info=True)
        logger.info("AOL object index sync disabled by runtime policy")
    try:
        from backend.app.services.capability_install_jobs import (
            run_capability_install_job_worker_loop,
        )

        if is_execution_plane():
            setattr(app.state, _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR, None)
            logger.info("Capability install job worker disabled on execution plane")
        else:
            capability_install_job_worker_task = asyncio.create_task(
                run_capability_install_job_worker_loop(app),
                name="capability-install-job-worker",
            )
            setattr(
                app.state,
                _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR,
                capability_install_job_worker_task,
            )
            logger.info("Capability install job worker task scheduled")
    except Exception as exc:
        setattr(app.state, _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR, None)
        logger.warning(
            "Failed to schedule capability install job worker: %s",
            exc,
            exc_info=True,
        )
    try:
        yield
    finally:
        await run_shutdown(app)
