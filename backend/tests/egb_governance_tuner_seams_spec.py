import asyncio
from types import SimpleNamespace

from backend.app.egb.components.governance_tuner import (
    ApplyResult,
    GovernanceSettings,
    GovernanceTuner,
)
from backend.app.egb.schemas.drift_report import DriftLevel


def test_governance_tuner_facade_exports_support_types():
    first = GovernanceSettings(strictness_level=1)
    second = GovernanceSettings()

    first.allowed_tools.append("tool-a")

    assert ApplyResult(success=True, applied_actions=[], failed_actions=[]).success is True
    assert GovernanceTuner.STRICTNESS_UPGRADE_THRESHOLD[DriftLevel.HIGH] == 2
    assert first.allowed_tools == ["tool-a"]
    assert second.allowed_tools == []
    assert second.denied_tools == []


def test_governance_tuner_generates_strictness_prescription_without_live_resources():
    async def run_case():
        drift_report = SimpleNamespace(
            intent_id="intent-1",
            run_id="run-1",
            workspace_id="workspace-1",
            drift_level=DriftLevel.HIGH,
        )
        return await GovernanceTuner().generate_prescription(
            drift_report,
            [],
            GovernanceSettings(strictness_level=0),
        )

    prescription = asyncio.run(run_case())

    assert prescription.intent_id == "intent-1"
    assert len(prescription.recommendations) == 1
    assert len(prescription.applicable_actions) == 1
    assert prescription.confidence == 0.75
    assert prescription.primary_recommendation.knob_type.value == "strictness"
    assert prescription.primary_recommendation.suggested_value == 2
