"""Normalize existing ingress context into a stable run intent envelope."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessKind,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunIntentEnvelope,
    RunIntentRiskClass,
    RunIntentSource,
    SideEffectClass,
)


def _list_value(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if item]


def _stable_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_harness(value: Any) -> RunHarnessKind | None:
    try:
        return RunHarnessKind(str(value)) if value else None
    except ValueError:
        return None


def _parse_side_effects(value: Any) -> list[SideEffectClass]:
    items = value if isinstance(value, list) else [value] if value else []
    parsed: list[SideEffectClass] = []
    for item in items:
        try:
            parsed.append(SideEffectClass(str(item)))
        except ValueError:
            continue
    return parsed


class RunIntentEnvelopeBuilder:
    def build_for_pipeline(
        self,
        *,
        decision_id: str,
        workspace_id: str,
        profile_id: str,
        intent_text: str,
        request: Any = None,
        workspace: Any = None,
        runtime_profile: Any = None,
    ) -> RunIntentEnvelope:
        action_params = getattr(request, "action_params", None)
        params = action_params if isinstance(action_params, dict) else {}
        context_refs = _list_value(params.get("context_object_refs"))
        writable_roots = _list_value(params.get("workspace_roots"))
        readonly_roots = _list_value(params.get("workspace_readonly_roots"))
        preferred_harness = _parse_harness(params.get("run_harness_kind"))
        if preferred_harness is None:
            if params.get("composition_graph_ref"):
                preferred_harness = RunHarnessKind.COMPOSITION_GRAPH
            elif params.get("workflow_code") or params.get("playbook_code"):
                preferred_harness = RunHarnessKind.DURABLE_WORKFLOW
            elif params.get("tool_ref") or params.get("tool_code"):
                preferred_harness = RunHarnessKind.DETERMINISTIC_TOOL

        side_effects = _parse_side_effects(params.get("requested_side_effects"))
        risk_value = params.get("risk_class", RunIntentRiskClass.LOW.value)
        try:
            risk_class = RunIntentRiskClass(str(risk_value))
        except ValueError:
            risk_class = RunIntentRiskClass.HIGH

        workspace_ref = getattr(workspace, "id", None) or workspace_id
        runtime_ref = getattr(runtime_profile, "id", None) or "workspace-runtime-profile"
        key_payload = {
            "decision_id": decision_id,
            "workspace_id": workspace_id,
            "profile_id": profile_id,
            "intent_text": intent_text,
            "preferred_harness": preferred_harness,
            "side_effects": side_effects,
        }
        idempotency_key = params.get("idempotency_key") or _stable_key(key_payload)
        trace_id = params.get("trace_id") or str(uuid.uuid4())
        return RunIntentEnvelope(
            decision_id=decision_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            origin_surface=RunIntentSource.CHAT,
            intent_text=intent_text,
            context_object_refs=context_refs,
            capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(
                ref=f"workspace:{workspace_ref}:capabilities"
            ),
            permission_profile_ref=RunHarnessPermissionProfileRef(
                ref=f"profile:{profile_id}:permissions"
            ),
            policy_bundle_ref=RunHarnessPolicyBundleRef(
                ref=f"runtime-profile:{runtime_ref}",
                version="v1",
            ),
            workspace_roots=writable_roots,
            workspace_readonly_roots=readonly_roots,
            data_classification=str(params.get("data_classification", "internal")),
            requested_side_effects=side_effects,
            approval_mode=str(params.get("approval_mode", "policy")),
            latency_budget_ms=params.get("latency_budget_ms"),
            cost_budget=params.get("cost_budget"),
            context_budget=params.get("context_budget"),
            delegation_depth_limit=int(params.get("delegation_depth_limit", 1)),
            idempotency_key=str(idempotency_key),
            trace_id=str(trace_id),
            preferred_harness=preferred_harness,
            risk_class=risk_class,
            metadata={"source": "pipeline_preview"},
        )

