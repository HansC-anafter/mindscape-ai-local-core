import os
import sys
from types import SimpleNamespace

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.services.decision.coordinator_support import (
    build_governance_decision_payload,
    serialize_playbook_contribution,
)
from backend.app.services.orchestration.governance_follow_up import (
    calculate_acceptance_pass_rate,
)
from backend.app.services.orchestration.meeting._prompt_context import (
    build_lens_context,
)


def test_serialize_playbook_contribution_preserves_required_and_optional_fields() -> None:
    contribution = SimpleNamespace(
        playbook_code="demo.playbook",
        status=SimpleNamespace(value="reject"),
        accepted=False,
        missing_inputs=["api_key"],
        clarification_questions=["which provider?"],
        rejection_reason="Missing API key",
        recommended_alternatives=["fallback.playbook"],
        recommended_orchestration="demo.orchestration",
    )

    payload = serialize_playbook_contribution(contribution)

    assert payload == {
        "playbook_code": "demo.playbook",
        "status": "reject",
        "accepted": False,
        "missing_inputs": ["api_key"],
        "clarification_questions": ["which provider?"],
        "rejection_reason": "Missing API key",
        "recommended_alternatives": ["fallback.playbook"],
        "recommended_orchestration": "demo.orchestration",
    }


def test_build_governance_decision_payload_handles_preflight_failures() -> None:
    decision_result = SimpleNamespace(
        cost_governance_contribution=None,
        node_governance_contribution=None,
        policy_contribution=None,
        playbook_contribution=SimpleNamespace(
            accepted=False,
            rejection_reason="Missing API key in environment",
            missing_inputs=["api_key"],
            recommended_alternatives=["fallback.playbook"],
        ),
        selected_playbook_code="demo.playbook",
        intent_contribution=SimpleNamespace(workspace_id="ws-1"),
    )

    payload = build_governance_decision_payload(
        coordinator=SimpleNamespace(cost_governance=None),
        decision_result=decision_result,
    )

    assert payload["type"] == "preflight_failed"
    assert payload["layer"] == "preflight"
    assert payload["preflight_failure"]["missing_inputs"] == ["api_key"]
    assert payload["preflight_failure"]["recommended_alternatives"] == [
        "fallback.playbook"
    ]
    assert payload["preflight_failure"]["missing_credentials"] == [
        "Missing API key in environment"
    ]


def test_calculate_acceptance_pass_rate_counts_only_acceptance_checks() -> None:
    eval_summary = {
        "checks": [
            {"test": "acceptance:artifact_exists", "passed": True},
            {"test": "acceptance:coverage", "passed": False},
            {"test": "quality:score", "passed": True},
        ]
    }

    assert calculate_acceptance_pass_rate(eval_summary) == 0.5


def test_build_lens_context_exposes_only_non_off_dimensions() -> None:
    lens = SimpleNamespace(
        global_preset_name="Focus",
        hash="lens-hash",
        nodes=[
            SimpleNamespace(
                state=SimpleNamespace(value="off"),
                node_label="Ignore Me",
                effective_scope="global",
            ),
            SimpleNamespace(
                state=SimpleNamespace(value="emphasize"),
                node_label="Accuracy",
                effective_scope="project",
            ),
            SimpleNamespace(
                state=SimpleNamespace(value="keep"),
                node_label="Tone",
                effective_scope="workspace",
            ),
        ],
    )

    context = build_lens_context(SimpleNamespace(_effective_lens=lens))

    assert "Active Lens: Focus" in context
    assert "Lens Hash: lens-hash" in context
    assert "Accuracy" in context
    assert "Total active dimensions: 2" in context
    assert "Ignore Me" not in context
