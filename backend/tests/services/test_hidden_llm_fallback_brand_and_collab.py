import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

services_module = types.ModuleType("services")
services_module.__path__ = []  # type: ignore[attr-defined]
site_hub_module = types.ModuleType("services.site_hub_client")
site_hub_module.SiteHubClient = object
sys.modules["services"] = services_module
sys.modules["services.site_hub_client"] = site_hub_module

from backend.app.services.cloud_connector.messaging_handler import MessagingHandler
from backend.app.services.personal_governance import digest_extraction as digest_extraction_module
from backend.app.services.multi_ai_collaboration import MultiAICollaborationService


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
brand_context_helper_module = _load_module(
    "test_brand_context_helper_module",
    _BACKEND_ROOT / "app/capabilities/brand_identity/api/brand_context_helper.py",
)
cis_mapper_endpoints_module = _load_module(
    "test_cis_mapper_endpoints_module",
    _BACKEND_ROOT / "app/capabilities/brand_identity/api/cis_mapper_endpoints.py",
)
MapDocumentRequest = cis_mapper_endpoints_module.MapDocumentRequest
map_document_to_cis = cis_mapper_endpoints_module.map_document_to_cis


@pytest.mark.asyncio
async def test_multi_ai_collaboration_skips_managed_seed_extraction_without_explicit_selection(
    monkeypatch,
):
    class _FakeStore:
        def get_profile(self, _profile_id):
            return SimpleNamespace(locale="en")

        async def get_workspace(self, _workspace_id):
            return SimpleNamespace(owner_user_id="profile-1")

    class _BombSeedExtractor:
        def __init__(self, *args, **kwargs):
            raise AssertionError("SeedExtractor should not be initialized")

    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        lambda: _FakeStore(),
    )
    monkeypatch.setattr(
        "backend.app.shared.llm_provider_helper.build_managed_llm_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("chat_model not configured")
        ),
    )
    monkeypatch.setattr(
        "backend.app.capabilities.semantic_seeds.services.seed_extractor.SeedExtractor",
        _BombSeedExtractor,
    )

    service = MultiAICollaborationService(
        file_processor=SimpleNamespace(),
        playbook_runner=SimpleNamespace(),
    )
    result = await service._analyze_semantic_seeds(
        file_info={
            "detected_type": "document",
            "name": "product-roadmap.pdf",
            "text_content": "A" * 300,
        },
        file_data="",
        file_name="product-roadmap.pdf",
        profile_id="profile-1",
        workspace_id="workspace-1",
    )

    assert result["enabled"] is True
    assert result["themes"] == ["document"]
    assert result["action"] == "add_to_mindscape"


@pytest.mark.asyncio
async def test_brand_context_auto_generation_skips_without_explicit_selection(
    monkeypatch,
):
    monkeypatch.setattr(
        brand_context_helper_module,
        "build_managed_llm_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("chat_model not configured")
        ),
    )

    result = await brand_context_helper_module._generate_basic_brand_assets(
        available_data={
            "workspace_title": "Demo Workspace",
            "workspace_description": "Description",
            "artifact_summaries": ["context"],
        },
        workspace_id="workspace-1",
        artifacts_store=SimpleNamespace(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_cis_mapper_requires_explicit_chat_model(monkeypatch):
    monkeypatch.setattr(
        cis_mapper_endpoints_module,
        "build_managed_llm_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("chat_model not configured")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await map_document_to_cis(
            MapDocumentRequest(
                document_content="brand brief",
                document_type="brief",
                workspace_id="workspace-1",
            )
        )

    assert exc_info.value.status_code == 422
    assert "explicit chat_model selection" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cis_mapper_uses_explicit_model_without_provider_default(monkeypatch):
    captured = {}

    class _FakeProvider:
        async def chat_completion(
            self,
            *,
            messages,
            model,
            temperature,
            max_tokens,
        ):
            captured["messages"] = messages
            captured["model"] = model
            captured["temperature"] = temperature
            captured["max_tokens"] = max_tokens
            return """
            {
              "brand_mi": {
                "vision": "Vision",
                "values": ["Value"],
                "worldview": "Worldview",
                "redlines": ["Redline"]
              },
              "personas": [],
              "storylines": []
            }
            """

    monkeypatch.setattr(
        cis_mapper_endpoints_module,
        "build_managed_llm_provider",
        lambda *args, **kwargs: (
            _FakeProvider(),
            SimpleNamespace(model_name="gpt-explicit", provider_name="openai"),
        ),
    )
    monkeypatch.setattr(cis_mapper_endpoints_module, "ARTIFACT_STORE_AVAILABLE", False)

    result = await map_document_to_cis(
        MapDocumentRequest(
            document_content="brand brief",
            document_type="brief",
            workspace_id="workspace-1",
        )
    )

    assert captured["model"] == "gpt-explicit"
    assert result.metadata["llm_model"] == "gpt-explicit"
    assert result.metadata["llm_provider"] == "openai"
    assert result.artifacts[0].kind == "brand_mi"


@pytest.mark.asyncio
async def test_digest_extraction_skips_without_explicit_backend_contract():
    result = await digest_extraction_module._call_extraction_llm(
        "system",
        "user",
    )

    assert result is None


@pytest.mark.asyncio
async def test_messaging_handler_truncates_without_hidden_llm_summary():
    handler = MessagingHandler(
        websocket=SimpleNamespace(),
        device_id="device-1",
    )
    long_reply = (
        "這是一段很長的回覆。" * 20
        + "最後一句補充說明，確認系統會走 deterministic truncation。"
    )

    result = await handler._generate_reply_summary(long_reply)

    assert len(result) <= 100
    assert result == handler._truncate_at_boundary(long_reply, max_len=100)


@pytest.mark.asyncio
async def test_messaging_handler_uses_explicit_summary_generator():
    async def _summary_generator(_reply_text: str) -> str:
        return "explicit summary"

    handler = MessagingHandler(
        websocket=SimpleNamespace(),
        device_id="device-1",
        summary_generator=_summary_generator,
    )

    result = await handler._generate_reply_summary("x" * 200)

    assert result == "explicit summary"
