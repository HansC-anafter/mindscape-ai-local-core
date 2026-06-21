from types import SimpleNamespace

from backend.app.services.decision import coordinator_support as support


class _ExecutionProfile:
    def model_dump(self):
        return {"mode": "fast"}


class _FakeCostGovernance:
    def _get_quota_settings(self, workspace_id: str):
        assert workspace_id == "ws_1"
        return {"daily_quota": 10.0}

    def _get_today_usage(self, workspace_id: str):
        assert workspace_id == "ws_1"
        return 4.0


class _FakeStore:
    def __init__(self):
        self.events = []

    def create_event(self, event):
        self.events.append(event)


def test_public_facade_exports_support_helpers() -> None:
    expected = (
        "build_final_decision_dict",
        "build_governance_decision_payload",
        "emit_branch_proposed_event",
        "emit_decision_required_event",
        "record_governance_decisions",
        "serialize_conflict",
        "serialize_governance_contribution",
        "serialize_playbook_contribution",
        "store_decision_to_intent_log",
    )

    missing = [name for name in expected if not hasattr(support, name)]

    assert missing == []


def test_build_final_decision_dict_preserves_payload_keys() -> None:
    decision_result = SimpleNamespace(
        decision_id="decision_1",
        selected_playbook_code="daily_planning",
        execution_profile=_ExecutionProfile(),
        intent_contribution=SimpleNamespace(
            to_dict=lambda: {"decision_id": "decision_1", "confidence": 0.91}
        ),
        playbook_contribution=SimpleNamespace(
            playbook_code="daily_planning",
            status="accepted",
            accepted=True,
            missing_inputs=[],
            clarification_questions=[],
            rejection_reason=None,
            recommended_alternatives=[],
        ),
        node_governance_contribution=SimpleNamespace(approved=True, reason="ok"),
        cost_governance_contribution=None,
        memory_contribution=None,
        policy_contribution=None,
        conflicts=[{"kind": "none"}],
        resolution_strategy="auto",
        can_auto_execute=True,
        requires_user_approval=False,
    )

    payload = support.build_final_decision_dict(decision_result)

    assert payload["selected_playbook_code"] == "daily_planning"
    assert payload["execution_profile"] == {"mode": "fast"}
    assert payload["intent_contribution"] == {
        "decision_id": "decision_1",
        "confidence": 0.91,
    }
    assert payload["playbook_contribution"]["accepted"] is True
    assert payload["node_governance_contribution"] == {
        "approved": True,
        "reason": "ok",
    }
    assert payload["conflicts"] == [{"kind": "none"}]
    assert payload["can_auto_execute"] is True


def test_build_governance_decision_payload_preserves_cost_shape() -> None:
    coordinator = SimpleNamespace(cost_governance=_FakeCostGovernance())
    decision_result = SimpleNamespace(
        workspace_id=None,
        intent_contribution=SimpleNamespace(workspace_id="ws_1"),
        cost_governance_contribution=SimpleNamespace(
            approved=False,
            reason="Please consider a cheaper profile",
            estimated_cost=2.5,
        ),
        node_governance_contribution=None,
        policy_contribution=None,
        playbook_contribution=None,
    )

    payload = support.build_governance_decision_payload(coordinator, decision_result)

    assert payload == {
        "type": "cost_exceeded",
        "layer": "cost",
        "approved": False,
        "reason": "Please consider a cheaper profile",
        "cost_governance": {
            "estimated_cost": 2.5,
            "quota_limit": 10.0,
            "current_usage": 4.0,
            "downgrade_suggestion": "Please consider a cheaper profile",
        },
    }


def test_emit_branch_proposed_event_uses_existing_store_event_path() -> None:
    store = _FakeStore()
    intent_decision = SimpleNamespace(
        decision_id="decision_1",
        alternatives=[
            SimpleNamespace(
                playbook_code="daily_planning",
                confidence=0.9,
                rationale="best match",
                required_inputs=["calendar"],
            ),
            SimpleNamespace(
                playbook_code="project_breakdown",
                confidence=0.6,
                rationale="fallback",
                required_inputs=[],
            ),
        ],
        suggested_playbook=None,
        rationale="branch rationale",
        decision_method="test",
    )

    support.emit_branch_proposed_event(
        store=store,
        intent_decision=intent_decision,
        workspace_id="ws_1",
        project_id="project_1",
        user_id="user_1",
    )

    assert len(store.events) == 1
    event = store.events[0]
    assert event.payload["branch_id"] == "branch-decision_1"
    assert event.payload["decision_id"] == "decision_1"
    assert event.payload["recommended_branch"] == "daily_planning"
    assert event.entity_ids == ["branch-decision_1", "decision_1"]
