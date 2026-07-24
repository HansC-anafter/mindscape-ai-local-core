import asyncio
import logging
import os
from typing import Any

from fastapi import FastAPI

from backend.app.app_bootstrap.startup_contract import (
    compute_db_fingerprint,
    delete_preflight_contract,
    is_contract_trustworthy,
    read_preflight_contract,
)
from backend.app.core.backend_runtime_mode import is_control_plane

logger = logging.getLogger(__name__)

_PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR = "_playbook_registry_post_ready_task"
_TOOL_RAG_POST_READY_TASK_ATTR = "_tool_rag_post_ready_task"
_PACK_VALIDATION_RESUME_TASK_ATTR = "_pack_validation_resume_task"
_RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR = "_runtime_migrations_post_ready_task"
_OBJECT_INDEX_SYNC_TASK_ATTR = "_object_index_sync_task"
_CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR = "_capability_install_job_worker_task"
_CODEX_POOL_SWEEPER_SERVICE_ATTR = "_codex_pool_sweeper_service"
_HOST_RESOURCE_REHYDRATE_TASK_ATTR = "_host_resource_rehydrate_task"
_HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR = "_host_resource_worker_reconcile_task"
_POST_READY_HEAVY_WORK_LOCK_ATTR = "_post_ready_heavy_work_lock"


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw_value, default)
        return default
    return max(minimum, min(value, maximum))


def _should_run_post_ready_playbook_registry_warmup() -> bool:
    raw_value = os.getenv("MINDSCAPE_PLAYBOOK_REGISTRY_POST_READY_MODE", "lazy")
    return raw_value.strip().lower() in {"eager", "true", "1", "yes"}


def should_run_object_index_sync() -> bool:
    disabled = os.getenv("AOL_OBJECT_INDEX_SYNC_DISABLED", "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False

    mode = os.getenv("AOL_OBJECT_INDEX_SYNC_MODE", "control").strip().lower()
    if mode in {"0", "false", "no", "off", "disabled", "none"}:
        return False
    if mode in {"all", "any"}:
        return True
    return is_control_plane()


def _core_database_accepts_work() -> tuple[bool, str | None]:
    try:
        from sqlalchemy import text

        from backend.app.database.engine import engine_postgres_core

        if engine_postgres_core is None:
            return False, "core PostgreSQL engine is not initialized"
        with engine_postgres_core.connect() as conn:
            in_recovery = bool(
                conn.execute(text("SELECT pg_is_in_recovery()")).scalar()
            )
        if in_recovery:
            return False, "core PostgreSQL is in recovery"
        return True, None
    except Exception as exc:
        return False, str(exc)


async def _wait_for_post_ready_bind_grace(task_name: str) -> None:
    """Let uvicorn finish binding before post-ready work starts."""
    delay_seconds = _env_int(
        "MINDSCAPE_POST_READY_BIND_GRACE_SECONDS",
        2,
        minimum=0,
        maximum=300,
    )
    if delay_seconds > 0:
        logger.info(
            "Post-ready task %s waiting %ds for server bind grace",
            task_name,
            delay_seconds,
        )
        await asyncio.sleep(delay_seconds)
    else:
        await asyncio.sleep(0)


def _get_post_ready_heavy_work_lock(app: FastAPI) -> asyncio.Lock:
    lock = getattr(app.state, _POST_READY_HEAVY_WORK_LOCK_ATTR, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(app.state, _POST_READY_HEAVY_WORK_LOCK_ATTR, lock)
    return lock


async def _run_post_ready_heavy_work(app: FastAPI, task_name: str, worker: Any):
    """Serialize post-ready heavy work off the API event loop."""
    async with _get_post_ready_heavy_work_lock(app):
        logger.info("Post-ready task %s heavy work starting", task_name)
        return await asyncio.to_thread(worker)


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
