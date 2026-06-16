import asyncio

from backend.app.app_bootstrap.lifecycle_common import (
    _CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR,
    _CODEX_POOL_SWEEPER_SERVICE_ATTR,
    _HOST_RESOURCE_REHYDRATE_TASK_ATTR,
    _HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR,
    _OBJECT_INDEX_SYNC_TASK_ATTR,
    _PACK_VALIDATION_RESUME_TASK_ATTR,
    _PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR,
    _POST_READY_HEAVY_WORK_LOCK_ATTR,
    _RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR,
    _TOOL_RAG_POST_READY_TASK_ATTR,
    _consume_preflight_contract_decision,
    _core_database_accepts_work,
    _env_int,
    _get_post_ready_heavy_work_lock,
    _run_post_ready_heavy_work,
    _should_run_post_ready_playbook_registry_warmup,
    _wait_for_post_ready_bind_grace,
    should_run_object_index_sync,
)
from backend.app.app_bootstrap.lifecycle_lifespan import lifespan
from backend.app.app_bootstrap.lifecycle_post_ready import (
    _rehydrate_host_resource_projection_post_ready,
    _resume_pending_pack_validations_post_ready,
    _run_object_index_sync_loop,
    _run_post_ready_playbook_registry_warmup,
    _run_post_ready_runtime_migrations,
    _run_post_ready_tool_rag_warmup,
    _sync_tool_rag_pack_embedding_state,
)
from backend.app.app_bootstrap.lifecycle_shutdown import run_shutdown
from backend.app.app_bootstrap.lifecycle_startup import run_startup
from backend.app.app_bootstrap.lifecycle_startup_services import (
    _run_compile_job_startup_recovery,
    _start_compile_job_startup_services,
)

__all__ = [
    "asyncio",
    "lifespan",
    "run_startup",
    "run_shutdown",
    "_env_int",
    "_should_run_post_ready_playbook_registry_warmup",
    "should_run_object_index_sync",
    "_core_database_accepts_work",
    "_wait_for_post_ready_bind_grace",
    "_get_post_ready_heavy_work_lock",
    "_run_post_ready_heavy_work",
    "_sync_tool_rag_pack_embedding_state",
    "_consume_preflight_contract_decision",
    "_run_post_ready_tool_rag_warmup",
    "_run_post_ready_playbook_registry_warmup",
    "_resume_pending_pack_validations_post_ready",
    "_run_post_ready_runtime_migrations",
    "_run_object_index_sync_loop",
    "_run_compile_job_startup_recovery",
    "_start_compile_job_startup_services",
    "_rehydrate_host_resource_projection_post_ready",
    "_PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR",
    "_TOOL_RAG_POST_READY_TASK_ATTR",
    "_PACK_VALIDATION_RESUME_TASK_ATTR",
    "_RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR",
    "_OBJECT_INDEX_SYNC_TASK_ATTR",
    "_CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR",
    "_CODEX_POOL_SWEEPER_SERVICE_ATTR",
    "_HOST_RESOURCE_REHYDRATE_TASK_ATTR",
    "_HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR",
    "_POST_READY_HEAVY_WORK_LOCK_ATTR",
]
