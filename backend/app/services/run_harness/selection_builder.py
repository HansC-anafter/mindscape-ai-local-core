"""Build auditable run harness selections from normalized intent."""

from backend.app.models.run_harness import (
    EscalationDisposition,
    RunHarnessKind,
    RunHarnessResourceEstimate,
    RunHarnessSelection,
    RunIntentEnvelope,
    RunIntentRiskClass,
    SideEffectClass,
)


class RunHarnessSelectionBuilder:
    POLICY_VERSION = "run_harness_selection.v1"

    def build(
        self,
        envelope: RunIntentEnvelope,
        harness_kind: RunHarnessKind,
        reason_codes: list[str],
        *,
        capability_misses: list[str] | None = None,
    ) -> RunHarnessSelection:
        side_effects = set(envelope.requested_side_effects)
        requires_approval = envelope.risk_class in {
            RunIntentRiskClass.HIGH,
            RunIntentRiskClass.CRITICAL,
        } or bool(
            side_effects
            & {
                SideEffectClass.SOFT_WRITE,
                SideEffectClass.EXTERNAL_WRITE,
                SideEffectClass.DESTRUCTIVE,
            }
        )
        requires_durability = harness_kind == RunHarnessKind.DURABLE_WORKFLOW
        requires_sandbox = harness_kind in {
            RunHarnessKind.DETERMINISTIC_TOOL,
            RunHarnessKind.DURABLE_WORKFLOW,
        } or bool(side_effects - {SideEffectClass.NONE, SideEffectClass.READONLY})
        fallback = (
            EscalationDisposition.QUEUE_MEETING
            if harness_kind != RunHarnessKind.MEETING_ESCALATION
            else EscalationDisposition.FAIL_CLOSED
        )
        return RunHarnessSelection(
            harness_kind=harness_kind,
            selection_reason_codes=reason_codes,
            requires_approval=requires_approval,
            requires_durability=requires_durability,
            requires_sandbox=requires_sandbox,
            selected_policy_version=self.POLICY_VERSION,
            fallback_strategy=fallback,
            capability_misses=capability_misses or [],
            resource_estimate=RunHarnessResourceEstimate(
                expected_latency_ms=envelope.latency_budget_ms,
                expected_cost_units=envelope.cost_budget,
                expected_context_tokens=envelope.context_budget,
                worker_slots=1 if requires_durability else 0,
            ),
        )

