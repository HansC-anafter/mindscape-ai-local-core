from pathlib import Path

from backend.app.app_bootstrap import lifecycle
from backend.app.app_bootstrap import lifecycle_common
from backend.app.app_bootstrap import lifecycle_lifespan
from backend.app.app_bootstrap import lifecycle_post_ready
from backend.app.app_bootstrap import lifecycle_shutdown
from backend.app.app_bootstrap import lifecycle_startup
from backend.app.app_bootstrap import lifecycle_startup_services


def test_lifecycle_facade_exports_legacy_entrypoints():
    names = [
        "lifespan",
        "run_startup",
        "run_shutdown",
        "_env_int",
        "_core_database_accepts_work",
        "should_run_object_index_sync",
        "_run_post_ready_playbook_registry_warmup",
        "_run_post_ready_tool_rag_warmup",
        "_run_post_ready_runtime_migrations",
        "_run_object_index_sync_loop",
        "_resume_pending_pack_validations_post_ready",
        "_rehydrate_host_resource_projection_post_ready",
        "_run_compile_job_startup_recovery",
        "_start_compile_job_startup_services",
        "_PLAYBOOK_REGISTRY_POST_READY_TASK_ATTR",
        "_TOOL_RAG_POST_READY_TASK_ATTR",
        "_PACK_VALIDATION_RESUME_TASK_ATTR",
        "_RUNTIME_MIGRATIONS_POST_READY_TASK_ATTR",
        "_OBJECT_INDEX_SYNC_TASK_ATTR",
        "_CAPABILITY_INSTALL_JOB_WORKER_TASK_ATTR",
        "_CODEX_POOL_SWEEPER_SERVICE_ATTR",
        "_HOST_RESOURCE_REHYDRATE_TASK_ATTR",
        "_HOST_RESOURCE_WORKER_RECONCILE_TASK_ATTR",
    ]

    for name in names:
        assert hasattr(lifecycle, name), name


def test_lifecycle_facade_points_to_single_owner_seams():
    assert lifecycle.lifespan is lifecycle_lifespan.lifespan
    assert lifecycle.run_startup is lifecycle_startup.run_startup
    assert lifecycle.run_shutdown is lifecycle_shutdown.run_shutdown
    assert lifecycle._env_int is lifecycle_common._env_int
    assert lifecycle._core_database_accepts_work is lifecycle_common._core_database_accepts_work
    assert lifecycle._run_post_ready_tool_rag_warmup is lifecycle_post_ready._run_post_ready_tool_rag_warmup
    assert lifecycle._run_post_ready_runtime_migrations is lifecycle_post_ready._run_post_ready_runtime_migrations
    assert lifecycle._start_compile_job_startup_services is lifecycle_startup_services._start_compile_job_startup_services


def test_main_uses_lifecycle_facade_import_path():
    main_source = (
        Path(__file__).resolve().parents[2] / "app" / "main.py"
    ).read_text(encoding="utf-8")

    assert "from backend.app.app_bootstrap.lifecycle import lifespan" in main_source
