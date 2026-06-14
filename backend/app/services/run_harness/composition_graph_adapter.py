"""Composition graph adapter for run harness compile and result contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.app.models.object_runtime.composition_graph import (
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphRun,
)
from backend.app.models.run_harness import (
    DurabilityMode,
    DurabilityRequirement,
    RunHarnessAttempt,
    RunHarnessEpisode,
    RunHarnessKind,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessSpec,
    RunHarnessStatus,
    RunHarnessStepEvent,
    RunHarnessTraceRef,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)


def _stable_ref(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:24]}"


class CompositionGraphHarnessAdapter:
    _RUN_STATUS_MAP = {
        "pending": RunHarnessStatus.PENDING,
        "running": RunHarnessStatus.RUNNING,
        "waiting": RunHarnessStatus.WAITING,
        "succeeded": RunHarnessStatus.SUCCEEDED,
        "failed": RunHarnessStatus.FAILED,
        "canceled": RunHarnessStatus.CANCELED,
    }
    _NODE_STATUS_MAP = {
        **_RUN_STATUS_MAP,
        "skipped": RunHarnessStatus.CANCELED,
    }

    def compile_spec(
        self,
        *,
        workspace_id: str,
        request: CompositionGraphCompileRequest,
        compiled: CompositionGraphCompileResponse,
    ) -> CompositionGraphCompileResponse:
        if compiled.status == "failed" or compiled.command_envelope is None:
            return compiled.model_copy(
                update={"output_mode": "run_harness_spec", "run_harness_spec": None}
            )
        envelope = compiled.command_envelope
        graph_ref_payload = envelope.metadata.get("composition_graph_ref") or {
            "graph_id": request.graph_id,
            "draft_id": request.draft_id,
        }
        graph_ref = _stable_ref("composition-graph", graph_ref_payload)
        intent_ref = _stable_ref(
            "run-intent",
            {
                "workspace_id": workspace_id,
                "command": request.command,
                "graph_ref": graph_ref,
            },
        )
        selection_ref = _stable_ref(
            "run-selection",
            {"harness_kind": RunHarnessKind.COMPOSITION_GRAPH.value, "graph_ref": graph_ref},
        )
        spec = RunHarnessSpec(
            spec_id=_stable_ref("run-harness-spec", {"intent": intent_ref}),
            graph_ref=graph_ref,
            intent_envelope_ref=intent_ref,
            selection_ref=selection_ref,
            required_tool_contract_refs=(
                [request.selected_pack_tool] if request.selected_pack_tool else []
            ),
            workspace_boundary_ref=f"workspace:{workspace_id}:boundary",
            policy_bundle_ref=f"workspace:{workspace_id}:policy-bundle",
            sandbox_profile_ref=f"workspace:{workspace_id}:sandbox-profile",
            durability_requirement=DurabilityRequirement(mode=DurabilityMode.CHECKPOINTED),
            trace_policy_ref="trace-policy:run-harness-v1",
        )
        return CompositionGraphCompileResponse(
            workspace_id=workspace_id,
            status="succeeded",
            output_mode="run_harness_spec",
            diagnostics=compiled.diagnostics,
            run_harness_spec=spec,
            metadata={
                **compiled.metadata,
                "legacy_command_envelope_available": True,
            },
        )

    def map_observation(
        self,
        *,
        workspace_id: str,
        run: CompositionGraphRun,
    ) -> RunHarnessObservation:
        return RunHarnessObservation(
            workspace_id=workspace_id,
            episode=self.map_episode(run),
            result=self.map_run(run),
            metadata={
                "graph_id": run.graph_id,
                "graph_run_id": run.id,
                "schema_version": run.schema_version,
            },
        )

    def map_episode(self, run: CompositionGraphRun) -> RunHarnessEpisode:
        mapped_status = self._RUN_STATUS_MAP[run.status]
        node_ids = list(run.node_states.keys())
        return RunHarnessEpisode(
            episode_id=f"composition-graph-episode:{run.id}",
            intent_envelope_ref=f"composition-graph-intent:{run.id}",
            selection_ref=f"composition-graph-selection:{run.id}",
            status=mapped_status,
            attempts=[
                RunHarnessAttempt(
                    attempt_id=f"composition-graph-attempt:{run.id}:1",
                    attempt_number=1,
                    status=mapped_status,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    step_events=[
                        RunHarnessStepEvent(
                            event_id=f"composition-graph-node:{run.id}:{node_id}",
                            event_type="composition_graph.node",
                            status=self._NODE_STATUS_MAP[node_state.status],
                            payload_ref=f"composition-graph-node:{run.id}:{node_id}",
                            occurred_at=(
                                node_state.completed_at
                                or node_state.started_at
                                or run.updated_at
                            ),
                        )
                        for node_id, node_state in run.node_states.items()
                    ],
                )
            ],
            trace_refs=[
                RunHarnessTraceRef(
                    trace_id=f"composition-graph:{run.id}",
                    node_ids=node_ids,
                )
            ],
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    def map_run(self, run: CompositionGraphRun) -> RunHarnessResult:
        mapped_status = self._RUN_STATUS_MAP[run.status]
        return RunHarnessResult(
            run_id=run.id,
            episode_id=f"composition-graph-episode:{run.id}",
            harness_kind=RunHarnessKind.COMPOSITION_GRAPH,
            status=mapped_status,
            output_artifact_refs=[
                str(value)
                for key, value in run.outputs.items()
                if key.endswith("_artifact_ref") and value
            ],
            metadata={"graph_id": run.graph_id, "schema_version": run.schema_version},
            wait_state=(
                RunHarnessWaitState(
                    kind=RunHarnessWaitKind.HUMAN_APPROVAL,
                    reason="Composition graph run is waiting for a resume signal.",
                )
                if mapped_status == RunHarnessStatus.WAITING
                else None
            ),
        )
