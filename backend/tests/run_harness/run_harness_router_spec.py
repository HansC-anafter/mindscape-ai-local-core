from backend.app.models.run_harness import (
    RunHarnessKind,
    RunIntentRiskClass,
    RunIntentSource,
)
from backend.app.services.run_harness.router import RunHarnessRouter


def test_router_fails_closed_for_unclassified_intent(run_intent) -> None:
    selection = RunHarnessRouter().select(run_intent)
    assert selection.harness_kind == RunHarnessKind.MEETING_ESCALATION
    assert selection.selection_reason_codes == ["unclassified_intent_fail_closed"]


def test_router_selects_graph_from_origin(run_intent) -> None:
    graph_intent = run_intent.model_copy(
        update={"origin_surface": RunIntentSource.COMPOSITION_GRAPH}
    )
    selection = RunHarnessRouter().select(graph_intent)
    assert selection.harness_kind == RunHarnessKind.COMPOSITION_GRAPH


def test_router_escalates_critical_risk(run_intent) -> None:
    critical = run_intent.model_copy(
        update={
            "preferred_harness": RunHarnessKind.DETERMINISTIC_TOOL,
            "risk_class": RunIntentRiskClass.CRITICAL,
        }
    )
    selection = RunHarnessRouter().select(critical)
    assert selection.harness_kind == RunHarnessKind.MEETING_ESCALATION

