import asyncio

import pytest

from backend.app.models.request_contract import RequestContract


class _HangingProvider:
    async def chat_completion(self, **kwargs):
        await asyncio.sleep(0.2)
        return "[]"


@pytest.mark.asyncio
async def test_compile_with_llm_times_out_and_falls_back(monkeypatch):
    from backend.features.workspace.chat.utils import llm_provider as llm_provider_module

    monkeypatch.setattr(
        llm_provider_module,
        "get_llm_provider_manager",
        lambda: object(),
    )
    monkeypatch.setattr(
        llm_provider_module,
        "get_llm_provider",
        lambda model_name, llm_provider_manager=None: (_HangingProvider(), None),
    )
    monkeypatch.setattr(RequestContract, "LLM_TIMEOUT_S", 0.01, raising=False)

    contract = await RequestContract.compile_with_llm(
        user_message="整理合作方向的 3 個關鍵點",
        agenda=["整理合作方向的 3 個關鍵點", "列出 2 到 3 個立即下一步"],
        workspace_id="ws-test",
        model_name="test-model",
    )

    assert [d.id for d in contract.deliverables] == ["D1", "D2"]
    assert [d.name for d in contract.deliverables] == [
        "整理合作方向的 3 個關鍵點",
        "列出 2 到 3 個立即下一步",
    ]
    assert contract.workspace_scope == "ws-test"
