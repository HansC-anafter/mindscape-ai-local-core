"""Tests verifying application bootstrap modularity and modern lifecycle."""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@pytest.mark.integration
def test_app_lifespan_manager():
    """P3: Validates that the application can boot using modern TestClient context manager.
    NOTE: This is a heavy integration test. It runs migrations, connects to Redis, OCR checks, etc.
    """
    from backend.app.main import app
    # Under the FastAPI TestClient, treating it as a context manager invokes lifespan
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

def test_cors_origin_regex():
    """P2: Validates the generated CORS regex accurately covers chrome extensions."""
    import re
    from backend.app.app_bootstrap.cors import get_cors_origin_regex
    
    regex = get_cors_origin_regex()
    assert regex is not None, "A regex must be provided for extensions"
    compiled = re.compile(regex)
    assert compiled.match("chrome-extension://abcdefghijklmnop")
    assert not compiled.match("http://malicious.com")

def test_routes_baseline():
    """P4: Validates strict route count baseline to prevent silent route drops."""
    from backend.app.main import app
    
    with TestClient(app) as client:
        response = client.get("/debug/routes")
        assert response.status_code == 200
        data = response.json()
        
        # Exact match required to detect both dropped routes and duplicate registrations.
        # This will need to be updated as new features are added.
        expected_route_count = 942  
        assert data["total_routes"] == expected_route_count, f"Route baseline breached. Expected {expected_route_count}, got {data['total_routes']}"


@pytest.mark.asyncio
async def test_root_health_payload_uses_fast_env_hints(monkeypatch):
    from backend.app.app_bootstrap.root_health import build_root_health_payload

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("DATABASE_URL_VECTOR", "postgresql://example/vector")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VERTEX_AI_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("VERTEX_AI_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_PROVIDER", raising=False)

    payload = await build_root_health_payload()

    assert payload["status"] == "healthy"
    assert payload["llm_configured"] is True
    assert payload["llm_available"] is True
    assert payload["llm_provider"] == "openai"
    assert payload["vector_db_connected"] is True
    assert payload["ocr_service"]["reason"] == "fast_root_health_probe"


class _FakeIssue:
    def __init__(self, severity: str):
        self.severity = severity

    def to_dict(self):
        return {"severity": self.severity}


class _FakeHealthChecker:
    async def _check_llm_configuration(self, *_args, **_kwargs):
        return {"configured": True, "available": True, "provider": "openai"}

    async def _check_vector_db(self, issues):
        issues.append(_FakeIssue("warning"))
        return {"connected": False}

    async def _check_backend_service(self, _issues):
        return {"status": "healthy"}


@pytest.mark.asyncio
async def test_root_health_payload_uses_detailed_checker_when_provided():
    from backend.app.app_bootstrap.root_health import build_root_health_payload

    payload = await build_root_health_payload(health_checker=_FakeHealthChecker())

    assert payload["status"] == "degraded"
    assert payload["llm_configured"] is True
    assert payload["vector_db_connected"] is False
    assert payload["issues"] == [{"severity": "warning"}]


@pytest.mark.asyncio
async def test_tool_rag_pack_embedding_sync_offloads_store_calls(monkeypatch):
    from backend.app.app_bootstrap.lifecycle import _sync_tool_rag_pack_embedding_state

    calls = []

    class _FakeToolEmbeddingService:
        async def get_capability_embedding_status(self, pack_id):
            calls.append(("status", pack_id))
            return {"row_count": 2, "latest_updated_at": f"{pack_id}-ts"}

    class _FakeActivationService:
        def record_embedding_observed(self, **kwargs):
            calls.append(("record", kwargs["pack_id"], kwargs["row_count"]))

    class _FakeInstalledPacksStore:
        def list_installed_pack_ids(self):
            calls.append(("list",))
            return ["ig", "brand_identity"]

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(("to_thread", getattr(func, "__name__", type(func).__name__)))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.app_bootstrap.lifecycle.asyncio.to_thread",
        fake_to_thread,
    )

    await _sync_tool_rag_pack_embedding_state(
        tool_embedding_service=_FakeToolEmbeddingService(),
        activation_service=_FakeActivationService(),
        installed_packs_store=_FakeInstalledPacksStore(),
    )

    assert ("list",) in calls
    assert ("status", "ig") in calls
    assert ("status", "brand_identity") in calls
    assert ("record", "ig", 2) in calls
    assert ("record", "brand_identity", 2) in calls


def test_consume_preflight_contract_decision_trusts_and_deletes(monkeypatch):
    from backend.app.app_bootstrap import lifecycle

    deleted = []
    contract = {
        "written_at": time.time(),
        "db_fingerprint": "fp-1",
        "db_ok": True,
        "critical_tables_ok": True,
    }

    monkeypatch.setattr(lifecycle, "read_preflight_contract", lambda: dict(contract))
    monkeypatch.setattr(lifecycle, "compute_db_fingerprint", lambda: "fp-1")
    monkeypatch.setattr(
        lifecycle,
        "delete_preflight_contract",
        lambda: deleted.append("deleted"),
    )

    trusted, reason, loaded = lifecycle._consume_preflight_contract_decision()

    assert trusted is True
    assert reason == "trusted"
    assert loaded == contract
    assert deleted == ["deleted"]


def test_preflight_detects_revision_graph_failure_markers():
    from backend.scripts.preflight_db import _is_revision_graph_failure

    assert _is_revision_graph_failure("KeyError: '20260311000000'") is True
    assert (
        _is_revision_graph_failure(
            "Revision 20260311000000 referenced from 20260322000000 is not present"
        )
        is True
    )
    assert _is_revision_graph_failure("ordinary migration timeout") is False


@pytest.mark.asyncio
async def test_refresh_tool_rag_corpus_ensures_table_before_index(monkeypatch):
    from backend.app.services.tool_rag_refresh import refresh_tool_rag_corpus

    calls = []

    class _FakeToolEmbeddingService:
        async def ensure_table(self):
            calls.append("ensure_table")

        async def ensure_indexed(self):
            calls.append("ensure_indexed")
            return 7

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.tool_embedding_service",
        SimpleNamespace(ToolEmbeddingService=_FakeToolEmbeddingService),
    )

    _tes, indexed_count, mode = await refresh_tool_rag_corpus(
        log_prefix="test refresh"
    )

    assert calls == ["ensure_table", "ensure_indexed"]
    assert indexed_count == 7
    assert mode == "ensure_indexed"


@pytest.mark.asyncio
async def test_refresh_tool_rag_corpus_falls_back_to_full_index(monkeypatch):
    from backend.app.services.tool_rag_refresh import refresh_tool_rag_corpus

    calls = []

    class _FakeToolEmbeddingService:
        async def ensure_table(self):
            calls.append("ensure_table")

        async def ensure_indexed(self):
            calls.append("ensure_indexed")
            raise RuntimeError("multimodel unavailable")

        async def index_all_tools(self):
            calls.append("index_all_tools")
            return 11

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.tool_embedding_service",
        SimpleNamespace(ToolEmbeddingService=_FakeToolEmbeddingService),
    )

    _tes, indexed_count, mode = await refresh_tool_rag_corpus(
        log_prefix="test refresh fallback"
    )

    assert calls == ["ensure_table", "ensure_indexed", "index_all_tools"]
    assert indexed_count == 11
    assert mode == "index_all_tools_fallback"


@pytest.mark.asyncio
async def test_lifespan_schedules_post_ready_tool_rag_task(monkeypatch):
    from backend.app.app_bootstrap import lifecycle

    app = FastAPI()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_startup(_app):
        return None

    async def fake_shutdown(_app):
        task = getattr(_app.state, lifecycle._TOOL_RAG_POST_READY_TASK_ATTR)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            cancelled.set()

    async def fake_warmup(_app):
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(lifecycle, "run_startup", fake_startup)
    monkeypatch.setattr(lifecycle, "run_shutdown", fake_shutdown)
    monkeypatch.setattr(lifecycle, "_run_post_ready_tool_rag_warmup", fake_warmup)

    async with lifecycle.lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        task = getattr(app.state, lifecycle._TOOL_RAG_POST_READY_TASK_ATTR)
        assert task.get_name() == "tool-rag-post-ready-warmup"
        assert task.done() is False

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_run_shutdown_cancels_post_ready_tool_rag_task(monkeypatch):
    from backend.app.app_bootstrap import lifecycle

    app = FastAPI()
    cancelled = asyncio.Event()

    async def fake_pending():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    setattr(
        app.state,
        lifecycle._TOOL_RAG_POST_READY_TASK_ATTR,
        asyncio.create_task(fake_pending()),
    )
    await asyncio.sleep(0)

    class _FakeDispatchManager:
        def stop_background_services(self):
            return None

    class _FakeCompileJobReconciler:
        def __init__(self, **_kwargs):
            return None

        def requeue_running_jobs_for_shutdown(self, *, job_ids):
            return {
                "inspected": len(job_ids),
                "requeued": 0,
                "session_reset": 0,
                "skipped": 0,
            }

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.compile_job_dispatch_manager",
        SimpleNamespace(get_compile_job_dispatch_manager=lambda: _FakeDispatchManager()),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.compile_job_reconciler",
        SimpleNamespace(CompileJobReconciler=_FakeCompileJobReconciler),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.compile_job_task_registry",
        SimpleNamespace(
            compile_job_task_registry=SimpleNamespace(
                snapshot=lambda: [],
                cancel=lambda _job_id: None,
                unregister=lambda _job_id: None,
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.compile_job_store",
        SimpleNamespace(CompileJobStore=lambda: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.meeting_session_store",
        SimpleNamespace(MeetingSessionStore=lambda: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.capabilities.performance_direction.services.scene_generation_dispatch_manager",
        SimpleNamespace(get_scene_generation_dispatch_manager=lambda: _FakeDispatchManager()),
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.routes.agent_dispatch",
        SimpleNamespace(get_agent_dispatch_manager=lambda: _FakeDispatchManager()),
    )

    await lifecycle.run_shutdown(app)

    assert cancelled.is_set()
