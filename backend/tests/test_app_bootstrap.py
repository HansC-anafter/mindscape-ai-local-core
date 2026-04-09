"""Tests verifying application bootstrap modularity and modern lifecycle."""
import pytest
from fastapi.testclient import TestClient

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
