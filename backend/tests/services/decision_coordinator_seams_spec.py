import asyncio
from pathlib import Path

from backend.app.services.decision.coordinator import (
    CostGovernanceDecision,
    IntentRoutingDecision,
    PlaybookCandidate,
    PlaybookPreflightResult,
    PolicyDecision,
    UnifiedDecisionCoordinator,
    UnifiedDecisionResult,
)


def _intent_decision(*, hint="fast", playbook_code="demo_playbook"):
    return IntentRoutingDecision(
        suggested_playbook=PlaybookCandidate(
            playbook_code=playbook_code,
            confidence=0.9,
            rationale="test",
        ),
        confidence=0.9,
        rationale="test",
        execution_profile_hint=hint,
    )


def _coordinator():
    return UnifiedDecisionCoordinator.__new__(UnifiedDecisionCoordinator)


def test_legacy_module_path_reexports_public_schema_and_facade():
    assert UnifiedDecisionCoordinator.__module__.endswith(".coordinator")
    assert IntentRoutingDecision.__name__ == "IntentRoutingDecision"
    assert UnifiedDecisionResult.__name__ == "UnifiedDecisionResult"


def test_execution_profile_builder_preserves_hint_and_cost_downgrade():
    coordinator = _coordinator()

    fast_profile = coordinator._build_execution_profile(_intent_decision(), None, None)
    durable_profile = coordinator._build_execution_profile(
        _intent_decision(hint="durable"),
        None,
        None,
    )
    human_profile = coordinator._build_execution_profile(
        _intent_decision(hint="human_review"),
        None,
        None,
    )
    rejected_profile = coordinator._build_execution_profile(
        _intent_decision(hint="human_review"),
        None,
        CostGovernanceDecision(approved=False),
    )

    assert fast_profile.execution_mode == "simple"
    assert fast_profile.side_effect_level == "low"
    assert durable_profile.execution_mode == "durable"
    assert durable_profile.supports_resume is True
    assert human_profile.requires_human_approval is True
    assert human_profile.side_effect_level == "high"
    assert rejected_profile.execution_mode == "simple"
    assert rejected_profile.requires_human_approval is False


def test_decision_synthesis_preserves_clarification_and_policy_rejection():
    coordinator = _coordinator()
    clarification = asyncio.run(
        coordinator._synthesize_decision(
            intent_decision=_intent_decision(),
            playbook_preflight_result=PlaybookPreflightResult(
                playbook_code="demo_playbook",
                status="need_clarification",
                accepted=False,
                clarification_questions=["Need input"],
            ),
            node_governance_decision=None,
            cost_governance_decision=None,
            memory_recommendation=None,
            policy_decision=None,
            context={},
        )
    )
    policy_rejected = asyncio.run(
        coordinator._synthesize_decision(
            intent_decision=_intent_decision(),
            playbook_preflight_result=None,
            node_governance_decision=None,
            cost_governance_decision=None,
            memory_recommendation=None,
            policy_decision=PolicyDecision(approved=False, reason="blocked"),
            context={},
        )
    )

    assert clarification.selected_playbook_code is None
    assert clarification.requires_user_approval is True
    assert clarification.execution_profile.side_effect_level == "none"
    assert policy_rejected.selected_playbook_code is None
    assert policy_rejected.requires_user_approval is False


def test_helper_modules_do_not_define_new_resource_paths():
    repo_root = Path(__file__).resolve().parents[3]
    source_paths = [
        "backend/app/services/decision/coordinator.py",
        "backend/app/services/decision/coordinator_models.py",
        "backend/app/services/decision/coordinator_decision_logic.py",
    ]
    helper_paths = source_paths[1:]
    disallowed_helper_markers = [
        "APIRouter",
        "router =",
        "@router",
        "create_engine",
        "sessionmaker",
        "psycopg2",
        "PgBouncer",
        "MindscapeStore",
        "IntentLog",
        "GovernanceDecisionRecorder",
        "create_event",
        "create_intent_log",
        "record_decision(",
        "record_cost_usage",
        "subprocess",
        "httpx",
        "requests",
        "setInterval",
        "asyncio.create_task",
        "Thread(",
        "Process(",
    ]

    for relative_path in helper_paths:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        for marker in disallowed_helper_markers:
            assert marker not in text
        assert "class UnifiedDecisionCoordinator" not in text

    facade_text = (repo_root / source_paths[0]).read_text(encoding="utf-8")
    assert facade_text.count("class UnifiedDecisionCoordinator") == 1
