"""Structured workflow gate decision contract tests."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.app.routes.core.execution_schemas import ResumeExecutionRequest
from backend.app.services.workflow.gate_decision import (
    MAX_DECISION_PAYLOAD_BYTES,
    build_approved_gate_decision,
)
from backend.app.services.workflow_template_engine import TemplateEngine


def test_approved_gate_decision_binds_exact_structured_payload():
    payload = {"approval": {"approval_id": "approval-001"}}

    decision = build_approved_gate_decision(
        comment="reviewed",
        decision_payload=payload,
        decision_payload_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["approval"],
            "properties": {"approval": {"type": "object"}},
        },
        decided_at="2026-07-27T00:00:00+00:00",
    )

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert decision["payload"] == payload
    assert decision["payload_sha256"] == hashlib.sha256(
        canonical
    ).hexdigest()


def test_gate_decision_rejects_oversized_payload():
    with pytest.raises(ValueError, match="gate_decision_payload_invalid"):
        build_approved_gate_decision(
            comment=None,
            decision_payload={"approval": "x" * MAX_DECISION_PAYLOAD_BYTES},
            decision_payload_schema=None,
            decided_at="2026-07-27T00:00:00+00:00",
        )


def test_reject_request_cannot_smuggle_decision_payload():
    with pytest.raises(
        ValueError,
        match="reject_decision_payload_forbidden",
    ):
        ResumeExecutionRequest(
            action="reject",
            decision_payload={"approval": {}},
        )


def test_decision_payload_resolves_as_raw_structured_step_input():
    decision = build_approved_gate_decision(
        comment=None,
        decision_payload={"approval": {"approval_id": "approval-001"}},
        decision_payload_schema=None,
        decided_at="2026-07-27T00:00:00+00:00",
    )
    step = SimpleNamespace(
        inputs={
            "approval": (
                "{{input.gate_decisions.validate_acceptance."
                "payload.approval}}"
            ),
            "decision_payload_sha256": (
                "{{input.gate_decisions.validate_acceptance."
                "payload_sha256}}"
            ),
        }
    )

    resolved = TemplateEngine.prepare_playbook_inputs(
        step,
        {"gate_decisions": {"validate_acceptance": decision}},
        {},
    )

    assert resolved["approval"] == {"approval_id": "approval-001"}
    assert resolved["decision_payload_sha256"] == decision[
        "payload_sha256"
    ]


def test_gate_decision_rejects_payload_outside_declared_schema():
    with pytest.raises(
        ValueError,
        match="gate_decision_payload_schema_mismatch",
    ):
        build_approved_gate_decision(
            comment=None,
            decision_payload={"unexpected": True},
            decision_payload_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["approval"],
                "properties": {"approval": {"type": "object"}},
            },
            decided_at="2026-07-27T00:00:00+00:00",
        )


def test_gate_decision_requires_payload_when_gate_declares_schema():
    with pytest.raises(
        ValueError,
        match="gate_decision_payload_required",
    ):
        build_approved_gate_decision(
            comment=None,
            decision_payload=None,
            decision_payload_schema={"type": "object"},
            decided_at="2026-07-27T00:00:00+00:00",
        )
