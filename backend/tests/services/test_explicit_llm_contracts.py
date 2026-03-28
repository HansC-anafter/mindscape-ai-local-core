from types import SimpleNamespace

import pytest

from backend.app.capabilities.core_llm.services.generate import run as generate_text
from backend.app.capabilities.core_llm.services.structured import extract as structured_extract
from backend.app.services.role_capability_mapper import map_capability_to_roles
from backend.app.shared.llm_utils import call_llm


@pytest.mark.asyncio
async def test_structured_extract_requires_explicit_provider():
    with pytest.raises(ValueError, match="explicit llm_provider"):
        await structured_extract(
            text="hello",
            schema_description="{}",
            model_name="gpt-5.4",
        )


@pytest.mark.asyncio
async def test_structured_extract_requires_explicit_model():
    with pytest.raises(ValueError, match="explicit model_name"):
        await structured_extract(
            text="hello",
            schema_description="{}",
            llm_provider=object(),
        )


@pytest.mark.asyncio
async def test_generate_requires_explicit_provider():
    with pytest.raises(ValueError, match="explicit llm_provider"):
        await generate_text(
            prompt="hello",
            model_name="gpt-5.4",
        )


@pytest.mark.asyncio
async def test_generate_requires_explicit_model():
    with pytest.raises(ValueError, match="explicit model_name"):
        await generate_text(
            prompt="hello",
            llm_provider=object(),
        )


@pytest.mark.asyncio
async def test_call_llm_requires_explicit_model():
    class _Provider:
        async def chat_completion(self, **kwargs):
            return "ok"

    with pytest.raises(ValueError, match="explicit model"):
        await call_llm(
            messages=[{"role": "user", "content": "hello"}],
            llm_provider=_Provider(),
            model=None,
        )


@pytest.mark.asyncio
async def test_role_capability_mapper_skips_llm_without_explicit_provider(monkeypatch):
    roles = [
        SimpleNamespace(
            id="mindscape_assistant",
            name="Mindscape Assistant",
            description="Default helper role",
        )
    ]

    class _RoleStore:
        def get_enabled_roles(self, profile_id):
            assert profile_id == "default-user"
            return roles

    monkeypatch.setattr(
        "backend.app.services.role_capability_mapper.AIRoleStore",
        lambda: _RoleStore(),
    )

    mappings = await map_capability_to_roles(
        capability_id="cap.demo",
        capability_name="Demo Capability",
        summary_for_roles="Demo summary",
        profile_id="default-user",
        target_language="zh-TW",
        llm_provider=None,
        model_name=None,
    )

    assert len(mappings) == 1
    assert mappings[0]["role_id"] == "mindscape_assistant"
    assert mappings[0]["is_fallback"] is True
