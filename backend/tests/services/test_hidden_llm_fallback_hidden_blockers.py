from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.conversation.context_builder.summary_policy import SummaryPolicy
from backend.app.services.execution_fallback_service import generate_fallback_artifact
from backend.app.services.playbook_optimization_service import (
    PlaybookOptimizationService,
)
import backend.app.shared.i18n_exporter as i18n_exporter_module


@pytest.mark.asyncio
async def test_export_i18n_requires_explicit_backend_and_model(tmp_path, monkeypatch):
    backend_dir = tmp_path / "app"
    source_dir = backend_dir / "i18n" / "playbooks"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "demo.en.yaml"
    source_file.write_text("title: Hello\n", encoding="utf-8")

    fake_file = backend_dir / "shared" / "i18n_exporter.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(i18n_exporter_module, "__file__", str(fake_file))

    with pytest.raises(ValueError, match="explicit llm_provider and model_name"):
        await i18n_exporter_module.export_i18n_for_locale(
            namespace="demo",
            source_locale="en",
            target_locale="ja",
        )


@pytest.mark.asyncio
async def test_summary_policy_skips_generation_without_explicit_backend():
    policy = SummaryPolicy(store=SimpleNamespace(), model_name="gpt-test")

    result = await policy.generate_and_store_summary(
        workspace_id="workspace-1",
        messages_to_summarize=["hello", "world"],
        profile_id="profile-1",
    )

    assert result is None


@pytest.mark.asyncio
async def test_playbook_optimization_service_skips_without_explicit_backend(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.app.services.playbook_optimization_service.MindscapeStore",
        lambda: SimpleNamespace(
            get_profile=lambda profile_id: SimpleNamespace(self_description={}),
            list_events=lambda profile_id, limit=100: [],
        ),
    )
    service = PlaybookOptimizationService()
    result = await service.generate_suggestions(
        profile_id="profile-1",
        playbook_code="demo_pack",
    )

    assert result == []


@pytest.mark.asyncio
async def test_execution_fallback_service_uses_template_without_explicit_backend(
    monkeypatch,
):
    stored = {}

    async def _fake_store(artifact, workspace_id, profile_id):
        stored["artifact"] = artifact
        stored["workspace_id"] = workspace_id
        stored["profile_id"] = profile_id

    monkeypatch.setattr(
        "backend.app.services.execution_fallback_service._store_artifact_as_event",
        _fake_store,
    )

    result = await generate_fallback_artifact(
        user_request="Write a launch announcement",
        workspace_id="workspace-1",
        profile_id="profile-1",
        expected_artifacts=["md"],
    )

    assert result["status"] == "success"
    assert result["artifact"]["type"] == "md"
    assert "Draft Document" in result["artifact"]["content"]
    assert stored["workspace_id"] == "workspace-1"
