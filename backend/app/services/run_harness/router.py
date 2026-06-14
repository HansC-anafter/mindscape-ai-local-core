"""Deterministic, selection-only run harness router."""

from backend.app.models.run_harness import (
    RunHarnessKind,
    RunHarnessSelection,
    RunIntentEnvelope,
    RunIntentRiskClass,
    RunIntentSource,
    SideEffectClass,
)
from backend.app.services.run_harness.selection_builder import (
    RunHarnessSelectionBuilder,
)


class RunHarnessRouter:
    def __init__(self, builder: RunHarnessSelectionBuilder | None = None) -> None:
        self.builder = builder or RunHarnessSelectionBuilder()

    def select(
        self,
        envelope: RunIntentEnvelope,
        *,
        capability_misses: list[str] | None = None,
    ) -> RunHarnessSelection:
        misses = capability_misses or []
        if misses:
            return self.builder.build(
                envelope,
                RunHarnessKind.MEETING_ESCALATION,
                ["capability_snapshot_miss"],
                capability_misses=misses,
            )
        if envelope.risk_class == RunIntentRiskClass.CRITICAL:
            return self.builder.build(
                envelope,
                RunHarnessKind.MEETING_ESCALATION,
                ["critical_risk_requires_escalation"],
            )
        if envelope.preferred_harness is not None:
            return self.builder.build(
                envelope,
                envelope.preferred_harness,
                ["explicit_harness_preference"],
            )
        if envelope.origin_surface == RunIntentSource.COMPOSITION_GRAPH:
            return self.builder.build(
                envelope,
                RunHarnessKind.COMPOSITION_GRAPH,
                ["composition_graph_origin"],
            )
        if envelope.origin_surface == RunIntentSource.WORKFLOW:
            return self.builder.build(
                envelope,
                RunHarnessKind.DURABLE_WORKFLOW,
                ["workflow_origin"],
            )
        if envelope.origin_surface == RunIntentSource.TOOL_RAIL:
            return self.builder.build(
                envelope,
                RunHarnessKind.DETERMINISTIC_TOOL,
                ["tool_rail_origin"],
            )
        if set(envelope.requested_side_effects) - {
            SideEffectClass.NONE,
            SideEffectClass.READONLY,
        }:
            return self.builder.build(
                envelope,
                RunHarnessKind.DETERMINISTIC_TOOL,
                ["bounded_side_effect_request"],
            )
        return self.builder.build(
            envelope,
            RunHarnessKind.MEETING_ESCALATION,
            ["unclassified_intent_fail_closed"],
        )

