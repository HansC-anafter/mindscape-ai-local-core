import json
from datetime import date, datetime

import pytest

from backend.app.services.governance.governance_projection import (
    build_cost_usage_summary,
    build_governance_metrics,
    calculate_rate,
    map_decision_row,
    map_execution_decision_row,
)


def _deserialize_json(value, default=None):
    if not value:
        return default
    return json.loads(value)


def test_decision_projection_preserves_public_and_execution_shapes():
    row = {
        "decision_id": "decision-1",
        "workspace_id": "workspace-1",
        "execution_id": "execution-1",
        "timestamp": datetime.fromisoformat("2026-06-16T01:00:00+00:00"),
        "layer": "policy",
        "approved": False,
        "reason": "role violation",
        "playbook_code": "demo",
        "metadata": json.dumps({"missing_inputs": True}),
    }

    public_decision = map_decision_row(row, deserialize_json=_deserialize_json)
    execution_decision = map_execution_decision_row(row, deserialize_json=_deserialize_json)

    assert "workspace_id" not in public_decision
    assert public_decision["timestamp"] == "2026-06-16T01:00:00+00:00"
    assert public_decision["approved"] is False
    assert public_decision["metadata"] == {"missing_inputs": True}
    assert execution_decision["workspace_id"] == "workspace-1"
    assert execution_decision["execution_id"] == "execution-1"


def test_cost_usage_summary_projects_rows_without_query_work():
    current_usage, trend, breakdown = build_cost_usage_summary(
        12.5,
        [(date(2026, 6, 15), 3), (date(2026, 6, 16), 9.5)],
        [("playbook-a", 7)],
        [("model-a", 5.5)],
    )

    assert current_usage == 12.5
    assert trend == [
        {"date": "2026-06-15", "cost": 3.0},
        {"date": "2026-06-16", "cost": 9.5},
    ]
    assert breakdown == {
        "by_playbook": {"playbook-a": 7.0},
        "by_model": {"model-a": 5.5},
    }


def test_governance_metrics_groups_rejections_violations_and_preflight_reasons():
    rejection_rate, cost_trend, violation_frequency, preflight_reasons = build_governance_metrics(
        [("cost", 4, 1), ("node", 2, 1), ("policy", 5, 2)],
        [(date(2026, 6, 16), 4.5)],
        [
            ("policy", "role violation", 2),
            ("policy", "domain rule", 3),
            ("node", "risk label", 4),
            ("node", "throttle limit", 5),
        ],
        [
            (json.dumps({"missing_inputs": True}), 2),
            (json.dumps({"missing_credentials": True, "environment_issues": True}), 1),
        ],
        deserialize_json=_deserialize_json,
    )

    assert calculate_rate(1, 4) == 25.0
    assert rejection_rate["cost"] == 25.0
    assert rejection_rate["node"] == 50.0
    assert rejection_rate["policy"] == 40.0
    assert rejection_rate["overall"] == pytest.approx(36.3636, rel=1e-4)
    assert cost_trend == [{"date": "2026-06-16", "cost": 4.5}]
    assert violation_frequency["policy"]["role_violation"] == 2
    assert violation_frequency["policy"]["data_domain_violation"] == 3
    assert violation_frequency["node"]["risk_label"] == 4
    assert violation_frequency["node"]["throttle"] == 5
    assert preflight_reasons == {
        "missing_inputs": 2,
        "missing_credentials": 1,
        "environment_issues": 1,
    }
