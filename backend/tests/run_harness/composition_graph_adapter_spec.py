from backend.app.models.object_runtime.composition_graph import (
    CompositionGraphCommandEnvelopeDraft,
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphRun,
    CompositionGraphRunNodeState,
)
from backend.app.services.run_harness.composition_graph_adapter import (
    CompositionGraphHarnessAdapter,
)


def test_graph_adapter_emits_ref_only_harness_spec() -> None:
    request = CompositionGraphCompileRequest(
        graph_id="graph-1",
        meeting_id="meeting-1",
        command="Run graph",
        output_mode="run_harness_spec",
    )
    compiled = CompositionGraphCompileResponse(
        workspace_id="workspace-1",
        status="succeeded",
        command_envelope=CompositionGraphCommandEnvelopeDraft(
            meeting_id="meeting-1",
            intent_text="Run graph",
            metadata={"composition_graph_ref": {"graph_id": "graph-1"}},
        ),
    )
    response = CompositionGraphHarnessAdapter().compile_spec(
        workspace_id="workspace-1",
        request=request,
        compiled=compiled,
    )
    assert response.output_mode == "run_harness_spec"
    assert response.command_envelope is None
    assert response.run_harness_spec.spec_version == "run_harness_spec.v1"
    assert response.run_harness_spec.graph_ref.startswith("composition-graph:")


def test_graph_adapter_maps_run_to_episode_result_observation() -> None:
    run = CompositionGraphRun(
        id="cg_run_1",
        graph_id="graph-1",
        workspace_id="workspace-1",
        status="waiting",
        node_states={
            "approval": CompositionGraphRunNodeState(
                node_id="approval",
                node_type="approval_gate",
                status="waiting",
            )
        },
        created_at="2026-06-14T00:00:00+00:00",
        updated_at="2026-06-14T00:00:01+00:00",
    )

    observation = CompositionGraphHarnessAdapter().map_observation(
        workspace_id="workspace-1",
        run=run,
    )

    assert observation.workspace_id == "workspace-1"
    assert observation.episode.episode_id == "composition-graph-episode:cg_run_1"
    assert observation.episode.status == "waiting"
    assert observation.episode.attempts[0].step_events[0].status == "waiting"
    assert observation.result.run_id == "cg_run_1"
    assert observation.result.status == "waiting"
    assert observation.result.wait_state.reason
