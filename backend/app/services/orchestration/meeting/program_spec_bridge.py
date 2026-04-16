"""
ProgramSpec bridge helpers for meeting runtime.

These helpers let the meeting engine progressively adopt ProgramSpec as a
runtime artifact without breaking the existing action-item based contract.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.models.action_intent import ActionIntent, IntentConfidence
from backend.app.models.program_spec import Milestone, ProgramSpec, Workstream
from backend.app.models.request_contract import ScaleEstimate
from backend.app.models.task_ir import PhaseIR, PhaseStatus

logger = logging.getLogger(__name__)


def parse_program_spec_from_output(
    executor_output: str,
    *,
    fallback_scale: ScaleEstimate = ScaleEstimate.STANDARD,
    coverage_snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[ProgramSpec]:
    """Parse a ProgramSpec-compatible payload from executor output.

    Accepts either:
    - a direct ProgramSpec-like object
    - a ProgramDraft-like object with workstreams + depends_on
    - an object wrapped under ``program_spec``
    """
    payload = _extract_json_payload(executor_output)
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("program_spec"), dict):
        payload = payload["program_spec"]

    raw_workstreams = payload.get("workstreams")
    if not isinstance(raw_workstreams, list) or not raw_workstreams:
        return None

    explicit_dependency_graph = payload.get("dependency_graph")
    dependency_graph: Dict[str, List[str]] = {}
    if isinstance(explicit_dependency_graph, dict):
        for workstream_id, depends_on in explicit_dependency_graph.items():
            dependency_graph[str(workstream_id)] = _normalize_string_list(depends_on)

    workstreams: List[Workstream] = []
    derived_targets: List[str] = _normalize_string_list(payload.get("target_outputs"))
    for index, raw_workstream in enumerate(raw_workstreams, start=1):
        if not isinstance(raw_workstream, dict):
            continue
        workstream_id = str(raw_workstream.get("id") or f"WS{index}").strip()
        if not workstream_id:
            continue
        dependency_graph.setdefault(
            workstream_id,
            _normalize_string_list(raw_workstream.get("depends_on")),
        )
        eligible_engines = _normalize_string_list(raw_workstream.get("eligible_engines"))
        if not eligible_engines:
            eligible_engines = _engine_candidates_from_raw_workstream(raw_workstream)
        workstreams.append(
            Workstream(
                id=workstream_id,
                name=str(raw_workstream.get("name") or workstream_id).strip(),
                description=str(
                    raw_workstream.get("description")
                    or raw_workstream.get("detail")
                    or ""
                ).strip(),
                produces_deliverables=_normalize_string_list(
                    raw_workstream.get("produces_deliverables")
                ),
                reviews_deliverables=_normalize_string_list(
                    raw_workstream.get("reviews_deliverables")
                ),
                consumes_deliverables=_normalize_string_list(
                    raw_workstream.get("consumes_deliverables")
                ),
                estimated_units=_safe_positive_int(
                    raw_workstream.get("estimated_units"), default=1
                ),
                unit_template=_coerce_optional_text(raw_workstream.get("unit_template")),
                eligible_engines=eligible_engines,
            )
        )
        if not payload.get("target_outputs"):
            derived_targets.extend(
                _normalize_string_list(raw_workstream.get("produces_deliverables"))
            )

    if not workstreams:
        return None

    milestones: List[Milestone] = []
    raw_milestones = payload.get("milestones")
    if isinstance(raw_milestones, list):
        for index, raw_milestone in enumerate(raw_milestones, start=1):
            if not isinstance(raw_milestone, dict):
                continue
            milestone_id = str(raw_milestone.get("id") or f"M{index}").strip()
            if not milestone_id:
                continue
            milestones.append(
                Milestone(
                    id=milestone_id,
                    name=str(raw_milestone.get("name") or milestone_id).strip(),
                    depends_on_streams=_normalize_string_list(
                        raw_milestone.get("depends_on_streams")
                    ),
                    deliverables=_normalize_string_list(
                        raw_milestone.get("deliverables")
                    ),
                )
            )

    return ProgramSpec(
        workstreams=workstreams,
        milestones=milestones,
        dependency_graph=dependency_graph,
        target_outputs=_normalize_string_list(derived_targets),
        scale=_coerce_scale(payload.get("scale")) or fallback_scale,
        coverage_snapshot=(
            payload.get("coverage_snapshot")
            if isinstance(payload.get("coverage_snapshot"), dict)
            else coverage_snapshot
        ),
    )


def bootstrap_program_spec_from_intents(
    intents: List[ActionIntent],
    *,
    decision: str = "",
    fallback_scale: ScaleEstimate = ScaleEstimate.STANDARD,
    coverage_snapshot: Optional[Dict[str, Any]] = None,
) -> ProgramSpec:
    """Build a minimal ProgramSpec from finalized ActionIntent objects."""
    workstreams: List[Workstream] = []
    dependency_graph: Dict[str, List[str]] = {}
    target_outputs: List[str] = []

    for intent in intents:
        workstream_id = str(intent.intent_id or "").strip()
        if not workstream_id:
            continue
        deliverable_ids = _deliverable_ids_from_intent(intent)
        dependency_graph[workstream_id] = list(intent.depends_on or [])
        target_outputs.append(intent.title)
        workstreams.append(
            Workstream(
                id=workstream_id,
                name=intent.title,
                description=intent.description,
                produces_deliverables=deliverable_ids,
                estimated_units=1,
                eligible_engines=_engine_candidates_from_intent(intent),
            )
        )

    if not target_outputs and decision.strip():
        target_outputs.append(decision.strip())

    return ProgramSpec(
        workstreams=workstreams,
        milestones=[],
        dependency_graph=dependency_graph,
        target_outputs=_normalize_string_list(target_outputs),
        scale=fallback_scale,
        coverage_snapshot=coverage_snapshot,
    )


def merge_program_spec_with_intents(
    program_spec: ProgramSpec,
    intents: List[ActionIntent],
) -> ProgramSpec:
    """Enrich ProgramSpec bindings from the finalized ActionIntent set."""
    intent_by_id = {
        str(intent.intent_id).strip(): intent
        for intent in intents
        if str(intent.intent_id or "").strip()
    }
    merged_workstreams: List[Workstream] = []
    merged_dependency_graph = dict(program_spec.dependency_graph)
    merged_target_outputs = _normalize_string_list(program_spec.target_outputs)
    seen_workstream_ids: set[str] = set()

    for workstream in program_spec.workstreams:
        seen_workstream_ids.add(workstream.id)
        intent = intent_by_id.get(workstream.id)
        if not intent:
            merged_workstreams.append(workstream)
            continue
        deliverable_ids = _deliverable_ids_from_intent(intent)
        engines = list(workstream.eligible_engines or [])
        for candidate in _engine_candidates_from_intent(intent):
            if candidate not in engines:
                engines.append(candidate)
        merged_dependency_graph[workstream.id] = list(intent.depends_on or [])
        merged_workstreams.append(
            workstream.model_copy(
                update={
                    "description": workstream.description or intent.description,
                    "produces_deliverables": (
                        workstream.produces_deliverables or deliverable_ids
                    ),
                    "eligible_engines": engines,
                }
            )
        )
        if intent.title not in merged_target_outputs:
            merged_target_outputs.append(intent.title)

    for intent_id, intent in intent_by_id.items():
        if intent_id in seen_workstream_ids:
            continue
        deliverable_ids = _deliverable_ids_from_intent(intent)
        merged_dependency_graph[intent_id] = list(intent.depends_on or [])
        merged_workstreams.append(
            Workstream(
                id=intent_id,
                name=intent.title,
                description=intent.description,
                produces_deliverables=deliverable_ids,
                estimated_units=1,
                eligible_engines=_engine_candidates_from_intent(intent),
            )
        )
        if intent.title not in merged_target_outputs:
            merged_target_outputs.append(intent.title)

    return program_spec.model_copy(
        update={
            "workstreams": merged_workstreams,
            "dependency_graph": merged_dependency_graph,
            "target_outputs": merged_target_outputs,
        }
    )


def action_intents_from_program_spec(
    program_spec: ProgramSpec,
    *,
    default_workspace_id: Optional[str] = None,
    deliverable_bindings: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[ActionIntent]:
    """Project ProgramSpec workstreams back into ActionIntent objects."""
    intents: List[ActionIntent] = []
    for workstream in program_spec.workstreams:
        preferred_engine, playbook_code, tool_name = _resolve_engine_binding(
            workstream.eligible_engines
        )
        deliverable_inputs = _build_workstream_deliverable_inputs(
            workstream=workstream,
            deliverable_bindings=deliverable_bindings or {},
            coverage_snapshot=program_spec.coverage_snapshot,
        )
        intents.append(
            ActionIntent(
                intent_id=workstream.id,
                title=workstream.name or workstream.id,
                description=workstream.description,
                target_workspace_id=default_workspace_id,
                depends_on=program_spec.dependency_graph.get(workstream.id) or None,
                playbook_code=playbook_code,
                tool_name=tool_name,
                engine=preferred_engine,
                confidence=(
                    IntentConfidence.HIGH
                    if playbook_code or tool_name
                    else IntentConfidence.MEDIUM
                ),
                input_params=deliverable_inputs or None,
            )
        )
    return intents


def phases_from_program_spec(
    program_spec: ProgramSpec,
    *,
    default_workspace_id: Optional[str] = None,
    deliverable_bindings: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[PhaseIR]:
    """Compile ProgramSpec workstreams into PhaseIR for dispatch."""
    phases: List[PhaseIR] = []
    for workstream in program_spec.workstreams:
        preferred_engine, _playbook_code, tool_name = _resolve_engine_binding(
            workstream.eligible_engines
        )
        deliverable_inputs = _build_workstream_deliverable_inputs(
            workstream=workstream,
            deliverable_bindings=deliverable_bindings or {},
            coverage_snapshot=program_spec.coverage_snapshot,
        )
        phases.append(
            PhaseIR(
                id=workstream.id,
                source_intent_id=workstream.id,
                name=workstream.name or workstream.id,
                description=workstream.description,
                status=PhaseStatus.PENDING,
                preferred_engine=preferred_engine or "agent:auto",
                depends_on=program_spec.dependency_graph.get(workstream.id) or None,
                target_workspace_id=default_workspace_id,
                tool_name=tool_name,
                input_params=deliverable_inputs or None,
            )
        )
    return phases


def _build_workstream_deliverable_inputs(
    *,
    workstream: Workstream,
    deliverable_bindings: Dict[str, Dict[str, Any]],
    coverage_snapshot: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    deliverable_ids = _normalize_string_list(workstream.produces_deliverables)
    if not deliverable_ids:
        deliverable_ids = _deliverable_ids_from_coverage_snapshot(
            coverage_snapshot=coverage_snapshot,
            workstream_id=workstream.id,
        )

    targets: List[Dict[str, Any]] = []
    for deliverable_id in deliverable_ids:
        binding = deliverable_bindings.get(deliverable_id) or {}
        target: Dict[str, Any] = {"deliverable_id": deliverable_id}
        deliverable_name = _coerce_optional_text(
            binding.get("deliverable_name") or binding.get("name")
        )
        deliverable_path = _coerce_optional_text(
            binding.get("deliverable_path")
            or binding.get("path")
            or binding.get("filename")
        )
        if deliverable_name:
            target["deliverable_name"] = deliverable_name
        if deliverable_path:
            target["deliverable_path"] = deliverable_path
        targets.append(target)

    if not targets:
        return {}

    if len(targets) == 1:
        return dict(targets[0])

    return {
        "deliverable_targets": targets,
        "deliverable_id": targets[0]["deliverable_id"],
        **(
            {"deliverable_name": targets[0]["deliverable_name"]}
            if targets[0].get("deliverable_name")
            else {}
        ),
        **(
            {"deliverable_path": targets[0]["deliverable_path"]}
            if targets[0].get("deliverable_path")
            else {}
        ),
    }


def _deliverable_ids_from_coverage_snapshot(
    *,
    coverage_snapshot: Optional[Dict[str, Any]],
    workstream_id: str,
) -> List[str]:
    if not isinstance(coverage_snapshot, dict):
        return []
    entries = coverage_snapshot.get("entries")
    if not isinstance(entries, list):
        return []
    deliverable_ids: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        covered_by = _normalize_string_list(entry.get("covered_by"))
        if workstream_id not in covered_by:
            continue
        deliverable_id = _coerce_optional_text(entry.get("deliverable_id"))
        if deliverable_id:
            deliverable_ids.append(deliverable_id)
    return _normalize_string_list(deliverable_ids)


def _extract_json_payload(text: str) -> Optional[Any]:
    stripped = str(text or "").strip()
    if not stripped:
        return None

    candidate_blocks: List[str] = [stripped]

    fenced_match = re.search(r"```(?:json)?\s*\n(.*?)```", stripped, re.DOTALL)
    if fenced_match:
        candidate_blocks.append(fenced_match.group(1).strip())

    for start, end in [("{", "}"), ("[", "]")]:
        start_idx = stripped.find(start)
        end_idx = stripped.rfind(end)
        if start_idx >= 0 and end_idx > start_idx:
            candidate_blocks.append(stripped[start_idx : end_idx + 1])

    for candidate in candidate_blocks:
        try:
            return json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _engine_candidates_from_raw_workstream(raw_workstream: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    preferred_engine = _coerce_optional_text(raw_workstream.get("preferred_engine"))
    if preferred_engine:
        candidates.append(preferred_engine)

    playbook_code = _coerce_optional_text(raw_workstream.get("playbook_code"))
    if playbook_code:
        candidates.append(f"playbook:{playbook_code}")

    tool_name = _coerce_optional_text(raw_workstream.get("tool_name"))
    if tool_name:
        candidates.append(f"tool:{tool_name}")

    return _normalize_string_list(candidates)


def _engine_candidates_from_intent(intent: ActionIntent) -> List[str]:
    candidates: List[str] = []
    if intent.engine:
        candidates.append(intent.engine)
    if intent.playbook_code:
        candidates.append(f"playbook:{intent.playbook_code}")
    if intent.tool_name:
        candidates.append(f"tool:{intent.tool_name}")
    return _normalize_string_list(candidates)


def _deliverable_ids_from_intent(intent: ActionIntent) -> List[str]:
    input_params = intent.input_params if isinstance(intent.input_params, dict) else {}
    deliverable_ids = _normalize_string_list([input_params.get("deliverable_id")])
    raw_targets = input_params.get("deliverable_targets")
    if isinstance(raw_targets, list):
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                continue
            deliverable_id = str(raw_target.get("deliverable_id") or "").strip()
            if deliverable_id:
                deliverable_ids.append(deliverable_id)
    return _normalize_string_list(deliverable_ids)


def _resolve_engine_binding(
    eligible_engines: List[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    preferred_engine: Optional[str] = None
    playbook_code: Optional[str] = None
    tool_name: Optional[str] = None

    for candidate in eligible_engines or []:
        value = str(candidate or "").strip()
        if not value:
            continue
        if preferred_engine is None:
            preferred_engine = value
        if value.startswith("playbook:") and playbook_code is None:
            playbook_code = value.split(":", 1)[1].strip() or None
        elif value.startswith("tool:") and tool_name is None:
            tool_name = value.split(":", 1)[1].strip() or None

    return preferred_engine, playbook_code, tool_name


def _coerce_scale(raw: Any) -> Optional[ScaleEstimate]:
    if raw is None:
        return None
    try:
        return ScaleEstimate(str(raw))
    except ValueError:
        return None


def _coerce_optional_text(raw: Any) -> Optional[str]:
    value = str(raw or "").strip()
    return value or None


def _normalize_string_list(values: Any) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _safe_positive_int(raw: Any, *, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
