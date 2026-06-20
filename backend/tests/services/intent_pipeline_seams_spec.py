from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.services.intent_analyzer as intent_analyzer_module
from backend.app.services.intent.execution_status_query import (
    build_current_tasks_snapshot,
)
from backend.app.services.intent.log_records import evaluate_intent_logs
from backend.app.services.intent_analyzer import (
    IntentAnalysisResult,
    IntentPipeline,
    TaskDomain,
)


def test_legacy_intent_analyzer_public_imports_remain_available():
    assert IntentPipeline.__name__ == "IntentPipeline"
    assert IntentAnalysisResult.__name__ == "IntentAnalysisResult"
    assert TaskDomain.UNKNOWN.value == "unknown"
    assert intent_analyzer_module._parse_json_from_response is not None


@pytest.mark.asyncio
async def test_execution_status_wrapper_delegates_to_helper(monkeypatch):
    provider = object()
    profile = object()
    pipeline = object.__new__(IntentPipeline)
    pipeline.llm_matcher = SimpleNamespace(llm_provider=provider)
    observed = {}

    async def fake_check_execution_status_query(**kwargs):
        observed.update(kwargs)
        return {"confidence": 0.99}

    monkeypatch.setattr(
        intent_analyzer_module,
        "check_execution_status_query",
        fake_check_execution_status_query,
    )

    result = await pipeline._check_execution_status_query("status", "workspace-1", profile)

    assert result == {"confidence": 0.99}
    assert observed == {
        "user_input": "status",
        "workspace_id": "workspace-1",
        "llm_provider": provider,
        "profile": profile,
    }


@pytest.mark.asyncio
async def test_multi_step_wrapper_delegates_to_helper(monkeypatch):
    provider = object()
    playbook_service = object()
    pipeline = object.__new__(IntentPipeline)
    pipeline.llm_matcher = SimpleNamespace(llm_provider=provider)
    pipeline.playbook_selector = SimpleNamespace(playbook_service=playbook_service)
    observed = {}

    async def fake_detect_multi_step_workflow(**kwargs):
        observed.update(kwargs)
        return {"is_multi_step": True, "workflow_steps": []}

    monkeypatch.setattr(
        intent_analyzer_module,
        "detect_multi_step_workflow",
        fake_detect_multi_step_workflow,
    )

    context = {"project_id": "project-1"}
    result = await pipeline._detect_multi_step_workflow(
        "make two assets", "asset_plan", context
    )

    assert result == {"is_multi_step": True, "workflow_steps": []}
    assert observed == {
        "user_input": "make two assets",
        "initial_playbook_code": "asset_plan",
        "context": context,
        "llm_provider": provider,
        "playbook_service": playbook_service,
    }


def test_task_snapshot_is_capped_to_ten_tasks():
    def task(pack_id: str, status: str):
        return SimpleNamespace(
            pack_id=pack_id,
            status=SimpleNamespace(value=status),
            created_at="2026-06-20T00:00:00Z",
        )

    running = [task(f"running-{index}", "running") for index in range(8)]
    pending = [task(f"pending-{index}", "pending") for index in range(8)]

    snapshot = build_current_tasks_snapshot(pending, running)
    lines = snapshot.splitlines()

    assert len(lines) == 10
    assert "running-0" in lines[0]
    assert "pending-1" in lines[-1]


def test_evaluate_intent_logs_returns_empty_metrics_without_annotations():
    store = SimpleNamespace(list_intent_logs=lambda **_: [])

    metrics = evaluate_intent_logs(store)

    assert metrics == {
        "total_logs": 0,
        "annotated_logs": 0,
        "accuracy": None,
        "layer1_accuracy": None,
        "layer2_accuracy": None,
        "layer3_accuracy": None,
        "confusion_matrix": {},
    }


def test_evaluate_intent_logs_preserves_annotated_metrics():
    annotated = [
        SimpleNamespace(
            final_decision={
                "interaction_type": "start_playbook",
                "task_domain": "content_writing",
                "selected_playbook_code": "content_plan",
            },
            user_override={
                "correct_interaction_type": "start_playbook",
                "correct_task_domain": "content_writing",
                "correct_playbook_code": "content_plan",
            },
        )
    ]

    def list_intent_logs(**kwargs):
        if kwargs["has_override"] is True:
            return annotated
        return annotated + [SimpleNamespace()]

    store = SimpleNamespace(list_intent_logs=list_intent_logs)

    metrics = evaluate_intent_logs(store)

    assert metrics["total_logs"] == 2
    assert metrics["annotated_logs"] == 1
    assert metrics["accuracy"] == 1.0
    assert metrics["layer1_accuracy"] == 1.0
    assert metrics["layer2_accuracy"] == 1.0
    assert metrics["layer3_accuracy"] == 1.0
    assert metrics["error_breakdown"] == {
        "layer1_errors": 0,
        "layer2_errors": 0,
        "layer3_errors": 0,
    }


def test_helper_modules_do_not_define_duplicate_resource_surfaces():
    repo_root = Path(__file__).resolve().parents[3]
    helper_paths = [
        repo_root / "backend/app/services/intent/workflow_detection.py",
        repo_root / "backend/app/services/intent/execution_status_query.py",
        repo_root / "backend/app/services/intent/log_records.py",
    ]
    forbidden_tokens = [
        "APIRouter",
        "router =",
        "router=",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "poll_interval",
        "setInterval",
        "class IntentPipeline",
        "def get_intent_pipeline",
    ]

    for helper_path in helper_paths:
        source = helper_path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in source, f"{token} unexpectedly found in {helper_path}"
