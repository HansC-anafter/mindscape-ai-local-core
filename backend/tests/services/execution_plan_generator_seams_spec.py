from pathlib import Path

from backend.app.models.workspace import ExecutionStep
from backend.app.services import execution_plan_context as context
from backend.app.services import execution_plan_generator as facade
from backend.app.services import execution_plan_models as plan_models
from backend.app.services import execution_plan_validation as validation


def test_facade_reexports_extracted_helpers() -> None:
    assert facade.EXECUTION_PLAN_PROMPT is context.EXECUTION_PLAN_PROMPT
    assert facade._parse_plan_json is validation._parse_plan_json
    assert facade._validate_and_reevaluate_plan is validation._validate_and_reevaluate_plan
    assert facade._convert_steps_to_tasks is plan_models._convert_steps_to_tasks
    assert facade._create_execution_plan is plan_models._create_execution_plan
    assert facade._create_minimal_plan is plan_models._create_minimal_plan


def test_parse_plan_json_accepts_direct_and_fenced_json() -> None:
    direct = validation._parse_plan_json('{"confidence": 0.8, "steps": []}')
    fenced = validation._parse_plan_json(
        '```json\n{"confidence": 0.6, "steps": [{"step_id": "S1"}]}\n```'
    )

    assert direct == {"confidence": 0.8, "steps": []}
    assert fenced == {"confidence": 0.6, "steps": [{"step_id": "S1"}]}
    assert validation._parse_plan_json("not json") is None


def test_convert_steps_to_tasks_preserves_valid_special_and_tool_paths() -> None:
    steps = [
        ExecutionStep(
            step_id="S1",
            intent="Analyze source posts",
            playbook_code="known_playbook",
            artifacts=["json"],
            reasoning="Use known pack",
        ),
        ExecutionStep(
            step_id="S2",
            intent="Extract semantic seeds",
            playbook_code="semantic_seeds",
            artifacts=["json"],
            reasoning="Special pack",
        ),
        ExecutionStep(
            step_id="S3",
            intent="Create a brief",
            tool_name="generic_drafting",
            artifacts=["md"],
            reasoning="Tool fallback",
            requires_confirmation=True,
            side_effect_level="soft_write",
        ),
        ExecutionStep(
            step_id="S4",
            intent="Use missing pack",
            playbook_code="missing_playbook",
            artifacts=["json"],
            reasoning="Invalid pack",
        ),
    ]

    tasks = facade._convert_steps_to_tasks(
        steps,
        plan_confidence=0.9,
        available_playbooks=[{"code": "known_playbook", "name": "Known"}],
    )

    assert [task.pack_id for task in tasks] == [
        "known_playbook",
        "semantic_seeds",
        "content_drafting",
    ]
    assert [task.task_type for task in tasks] == [
        "extract_intents",
        "extract_intents",
        "generate_draft",
    ]
    assert tasks[2].requires_cta is True
    assert tasks[2].auto_execute is False
    assert tasks[0].params["llm_analysis"] == {"confidence": 0.9}


def test_create_execution_plan_preserves_core_fields_and_tasks() -> None:
    plan = facade._create_execution_plan(
        plan_data={
            "user_request_summary": "Summarize workspace",
            "reasoning": "Need a structured plan",
            "plan_summary": "Analyze then draft",
            "confidence": 0.75,
            "steps": [
                {
                    "step_id": "S1",
                    "intent": "Analyze workspace",
                    "playbook_code": "workspace_analyzer",
                    "artifacts": ["json"],
                    "reasoning": "Read context",
                    "side_effect_level": "readonly",
                }
            ],
        },
        workspace_id="workspace-1",
        message_id="message-1",
        execution_mode="execution",
        available_playbooks=[{"playbook_code": "workspace_analyzer"}],
    )

    assert plan.workspace_id == "workspace-1"
    assert plan.message_id == "message-1"
    assert plan.execution_mode == "execution"
    assert plan.confidence == 0.75
    assert len(plan.steps) == 1
    assert len(plan.tasks) == 1
    assert plan.tasks[0].pack_id == "workspace_analyzer"


def test_helper_modules_do_not_define_duplicate_resource_surfaces() -> None:
    helper_modules = [context, validation, plan_models]
    forbidden_markers = [
        "APIRouter(",
        "@router",
        "create_task(",
        "Queue(",
        "pool_size",
        "pgbouncer",
        "polling_interval",
        "setInterval",
    ]

    for module in helper_modules:
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "def generate_execution_plan(" not in source
        for marker in forbidden_markers:
            assert marker not in source
