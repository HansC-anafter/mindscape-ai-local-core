#!/usr/bin/env python3
"""Validate Wave 2-4 meeting closure trace artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

TERMINAL_SESSION_STATUSES = {"closed", "failed"}
TERMINAL_JOB_STATUSES = {"succeeded", "failed"}
VALID_ROUTING_HEALTH = {"healthy", "warning", "critical"}
VALID_PROMPT_MODES = {"sparse", "compressed_sparse", "full_context_fallback"}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _nonempty_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _between_zero_and_one(value: Any) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 1


def _coerce_nonnegative_int(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _event_type_counts(events_payload: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    events = _coerce_list(_coerce_dict(events_payload).get("events"))
    for event in events:
        event_type = _nonempty_text(_coerce_dict(event).get("event_type"))
        if not event_type:
            continue
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _detect_environment_restart(
    *,
    session_metadata: Dict[str, Any],
    summary: Dict[str, Any],
    backend_runtime_before: Dict[str, Any],
    backend_runtime_after: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: List[str] = []

    before_container_id = _nonempty_text(backend_runtime_before.get("container_id"))
    after_container_id = _nonempty_text(backend_runtime_after.get("container_id"))
    before_started_at = _nonempty_text(backend_runtime_before.get("started_at"))
    after_started_at = _nonempty_text(backend_runtime_after.get("started_at"))
    summary_reason = _nonempty_text(summary.get("environment_restart_reason"))
    pipeline_failure = _coerce_dict(session_metadata.get("pipeline_failure"))
    pipeline_failure_stage = _nonempty_text(pipeline_failure.get("stage"))

    if before_container_id and after_container_id and before_container_id != after_container_id:
        reasons.append("backend_container_id_changed")
    if before_started_at and after_started_at and before_started_at != after_started_at:
        reasons.append("backend_container_started_at_changed")
    if pipeline_failure_stage == "startup_recovery":
        reasons.append("startup_recovery")
    if summary_reason and summary_reason not in reasons:
        reasons.append(summary_reason)

    return {
        "detected": bool(reasons),
        "reasons": reasons,
        "pipeline_failure_stage": pipeline_failure_stage,
        "before_container_id": before_container_id,
        "after_container_id": after_container_id,
        "before_started_at": before_started_at,
        "after_started_at": after_started_at,
    }


def _parse_compile_response_body(compile_response: Dict[str, Any]) -> Dict[str, Any]:
    body_raw = compile_response.get("body_raw")
    if isinstance(body_raw, dict):
        return body_raw
    if not isinstance(body_raw, str):
        return {}
    try:
        parsed = json.loads(body_raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _check(
    checks: List[Dict[str, Any]],
    *,
    name: str,
    passed: bool,
    message: str,
    wave: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    checks.append(
        {
            "name": name,
            "wave": wave,
            "passed": passed,
            "message": message,
            "details": details or {},
        }
    )


def _require_json(
    trace_dir: Path,
    relative_path: str,
    checks: List[Dict[str, Any]],
    *,
    wave: str,
    required: bool = True,
) -> Optional[Any]:
    path = trace_dir / relative_path
    if not path.is_file():
        _check(
            checks,
            name=f"{wave}.artifact.{relative_path}",
            passed=not required,
            message=(
                f"Missing required artifact: {relative_path}"
                if required
                else f"Optional artifact absent: {relative_path}"
            ),
            wave=wave,
            details={"path": str(path)},
        )
        return None
    try:
        payload = _load_json(path)
    except Exception as exc:  # pragma: no cover - defensive path
        _check(
            checks,
            name=f"{wave}.artifact.{relative_path}",
            passed=False,
            message=f"Failed to load JSON artifact: {relative_path}",
            wave=wave,
            details={"path": str(path), "error": str(exc)},
        )
        return None
    _check(
        checks,
        name=f"{wave}.artifact.{relative_path}",
        passed=True,
        message=f"Loaded artifact: {relative_path}",
        wave=wave,
        details={"path": str(path)},
    )
    return payload


def validate_trace(
    trace_dir: Path,
    *,
    require_closed: bool = False,
    require_dynamic_routing: bool = False,
) -> Dict[str, Any]:
    trace_dir = trace_dir.resolve()
    checks: List[Dict[str, Any]] = []

    summary = _require_json(
        trace_dir, "summary.json", checks, wave="wave2", required=False
    )
    provider_status_check = _require_json(
        trace_dir,
        "00_provider_status_check.json",
        checks,
        wave="wave2",
        required=False,
    )
    summary = _coerce_dict(summary)
    summary_provider_status = _coerce_dict(summary.get("provider_status"))
    terminal_state = _nonempty_text(summary.get("terminal_state")) or ""
    provider_status_reason = (
        _nonempty_text(provider_status_check.get("reason"))
        or _nonempty_text(summary_provider_status.get("reason"))
        or ""
    )
    preflight_failed = terminal_state == "preflight_failed"

    compile_response = _require_json(
        trace_dir,
        "02_compile_response.json",
        checks,
        wave="wave2",
        required=not preflight_failed,
    )
    acceptance = _require_json(
        trace_dir,
        "02a_compile_acceptance.json",
        checks,
        wave="wave2",
        required=not preflight_failed,
    )
    compile_job = _require_json(
        trace_dir,
        "02c_compile_job.json",
        checks,
        wave="wave2",
        required=not preflight_failed,
    )
    session = _require_json(
        trace_dir,
        "03_session_after_close.json",
        checks,
        wave="wave2",
        required=not preflight_failed,
    )
    events_payload = _require_json(
        trace_dir,
        "04_session_events.json",
        checks,
        wave="wave2",
        required=not preflight_failed,
    )
    backend_runtime_before = _require_json(
        trace_dir,
        "00_backend_runtime_before.json",
        checks,
        wave="wave2",
        required=False,
    )
    backend_runtime_after = _require_json(
        trace_dir,
        "11_backend_runtime_after.json",
        checks,
        wave="wave2",
        required=False,
    )

    compile_response = _coerce_dict(compile_response)
    provider_status_check = _coerce_dict(provider_status_check)
    acceptance = _coerce_dict(acceptance)
    compile_job = _coerce_dict(compile_job)
    session = _coerce_dict(session)
    events_payload = _coerce_dict(events_payload)
    backend_runtime_before = _coerce_dict(backend_runtime_before)
    backend_runtime_after = _coerce_dict(backend_runtime_after)

    compile_body = _parse_compile_response_body(compile_response)
    compile_job_id = (
        _nonempty_text(compile_body.get("compile_job_id"))
        or _nonempty_text(compile_body.get("job_id"))
        or _nonempty_text(acceptance.get("compile_job_id"))
        or _nonempty_text(summary.get("compile_job_id"))
    )
    compile_job_alias = _nonempty_text(compile_body.get("job_id"))
    session_id = (
        _nonempty_text(compile_body.get("session_id"))
        or _nonempty_text(acceptance.get("session_id"))
        or _nonempty_text(summary.get("session_id"))
        or _nonempty_text(session.get("id"))
    )
    session_status = _nonempty_text(session.get("status")) or ""
    compile_job_status = (
        _nonempty_text(compile_job.get("status"))
        or _nonempty_text(summary.get("compile_job_status"))
        or ""
    )
    event_counts = _event_type_counts(events_payload)
    session_metadata = _coerce_dict(session.get("metadata"))
    last_program_spec = _coerce_dict(session_metadata.get("last_program_spec"))
    last_program_spec_workstreams = _coerce_list(last_program_spec.get("workstreams"))
    program_spec_source = (
        _nonempty_text(session_metadata.get("last_program_spec_source"))
        or _nonempty_text(summary.get("program_spec_source"))
        or ""
    )
    program_spec_workstream_count = _coerce_nonnegative_int(
        session_metadata.get("last_program_spec_workstream_count"),
        default=_coerce_nonnegative_int(
            summary.get("program_spec_workstream_count"),
            default=len(last_program_spec_workstreams),
        ),
    )
    program_spec_target_outputs = _coerce_list(last_program_spec.get("target_outputs"))
    environment_restart = _detect_environment_restart(
        session_metadata=session_metadata,
        summary=summary,
        backend_runtime_before=backend_runtime_before,
        backend_runtime_after=backend_runtime_after,
    )
    restart_evidence_expected = bool(
        environment_restart["pipeline_failure_stage"]
        or backend_runtime_before
        or backend_runtime_after
        or summary.get("environment_restart_detected")
    )

    if provider_status_check:
        provider_required = bool(provider_status_check.get("required"))
        provider_available = bool(provider_status_check.get("available"))
        provider_matched = bool(provider_status_check.get("matched"))
        _check(
            checks,
            name="wave2.environment.provider_status_recorded",
            passed=True,
            message="Provider-status probe result was recorded",
            wave="wave2",
            details=provider_status_check,
        )
        _check(
            checks,
            name="wave2.environment.provider_status_requirement",
            passed=(provider_available and provider_matched) if provider_required else True,
            message=(
                "Provider-status requirement satisfied"
                if provider_required
                else "Provider-status probe is advisory for closure validation"
            ),
            wave="wave2",
            details=provider_status_check,
        )
    if preflight_failed:
        _check(
            checks,
            name="wave2.preflight.mainline_reached",
            passed=False,
            message="Closure preflight reached compile mainline",
            wave="wave2",
            details={
                "terminal_state": terminal_state,
                "provider_status_reason": provider_status_reason or None,
            },
        )
        _check(
            checks,
            name="wave2.environment.workspace_codex_cli_ready",
            passed=provider_status_reason != "workspace_codex_cli_not_observed",
            message="Workspace exposes an authenticated codex_cli surface before compile starts",
            wave="wave2",
            details={
                "provider_status_reason": provider_status_reason or None,
                "provider_status_check": provider_status_check or None,
            },
        )
        if require_dynamic_routing:
            _check(
                checks,
                name="wave3.routing.preflight_reached",
                passed=False,
                message="Dynamic routing validation requires closure to pass preflight and reach compile mainline",
                wave="wave3",
                details={
                    "terminal_state": terminal_state,
                    "provider_status_reason": provider_status_reason or None,
                },
            )
            _check(
                checks,
                name="wave4.prompt_mode.preflight_reached",
                passed=False,
                message="Prompt-mode validation requires closure to pass preflight and reach deliberation",
                wave="wave4",
                details={
                    "terminal_state": terminal_state,
                    "provider_status_reason": provider_status_reason or None,
                },
            )

        wave_status: Dict[str, str] = {}
        for wave in ("wave2", "wave3", "wave4"):
            wave_checks = [check for check in checks if check["wave"] == wave]
            if not wave_checks:
                wave_status[wave] = "not_applicable"
                continue
            wave_status[wave] = "passed" if all(check["passed"] for check in wave_checks) else "failed"

        passed = all(check["passed"] for check in checks)
        return {
            "trace_dir": str(trace_dir),
            "passed": passed,
            "require_closed": require_closed,
            "require_dynamic_routing": require_dynamic_routing,
            "summary": {
                "session_id": session_id,
                "session_status": session_status,
                "compile_job_id": compile_job_id,
                "compile_job_status": compile_job_status,
                "terminal_state": terminal_state,
                "environment_restart_detected": False,
                "environment_restart_reasons": [],
                "pipeline_failure_stage": None,
                "environment_blocker": provider_status_reason or "preflight_failed",
                "provider_status_check": provider_status_check or None,
                "event_counts": event_counts,
                "wave_status": wave_status,
            },
            "checks": checks,
        }

    _check(
        checks,
        name="wave2.compile.accepted_http",
        passed=compile_response.get("http_status") == 202,
        message="Compile ingress returned 202 Accepted",
        wave="wave2",
        details={"http_status": compile_response.get("http_status")},
    )
    _check(
        checks,
        name="wave2.compile.ids_present",
        passed=bool(compile_job_id and session_id),
        message="Compile accepted response exposed compile_job_id/job_id and session_id",
        wave="wave2",
        details={"compile_job_id": compile_job_id, "session_id": session_id},
    )
    _check(
        checks,
        name="wave2.compile.job_id_alias_consistent",
        passed=(compile_job_alias is None) or (compile_job_alias == compile_job_id),
        message="job_id alias matches compile_job_id when present",
        wave="wave2",
        details={"job_id": compile_job_alias, "compile_job_id": compile_job_id},
    )
    _check(
        checks,
        name="wave2.session.terminal_truth_consistent",
        passed=(
            session_status in TERMINAL_SESSION_STATUSES
            and terminal_state == session_status
            and (_nonempty_text(session.get("id")) == session_id)
        ),
        message="Session detail and summary agree on terminal truth",
        wave="wave2",
        details={
            "session_status": session_status,
            "summary_terminal_state": terminal_state,
            "session_id": _nonempty_text(session.get("id")),
            "summary_session_id": session_id,
        },
    )
    _check(
        checks,
        name="wave2.job.terminal_truth_consistent",
        passed=(
            compile_job_status in TERMINAL_JOB_STATUSES
            and _nonempty_text(compile_job.get("session_id")) == session_id
            and (
                (session_status == "closed" and compile_job_status == "succeeded")
                or (session_status == "failed" and compile_job_status == "failed")
            )
        ),
        message="Compile job terminal status matches session terminal status",
        wave="wave2",
        details={
            "compile_job_status": compile_job_status,
            "compile_job_session_id": _nonempty_text(compile_job.get("session_id")),
            "session_status": session_status,
        },
    )
    _check(
        checks,
        name="wave2.events.meeting_end_present",
        passed=event_counts.get("meeting_end", 0) >= 1,
        message="Meeting event trace contains meeting_end",
        wave="wave2",
        details={"event_counts": event_counts},
    )
    _check(
        checks,
        name="wave2.program_spec.present",
        passed=bool(last_program_spec) and program_spec_workstream_count >= 1,
        message="Session metadata persists last_program_spec with at least one workstream",
        wave="wave2",
        details={
            "program_spec_source": program_spec_source or None,
            "workstream_count": program_spec_workstream_count,
        },
    )
    _check(
        checks,
        name="wave2.program_spec.source_recorded",
        passed=program_spec_source in {"executor_structured", "action_intent_bootstrap"},
        message="ProgramSpec persistence records whether the run exercised structured or bootstrap path",
        wave="wave2",
        details={"program_spec_source": program_spec_source or None},
    )
    _check(
        checks,
        name="wave2.program_spec.target_outputs_present",
        passed=bool(program_spec_target_outputs),
        message="ProgramSpec captures target_outputs for downstream dispatch and inspection",
        wave="wave2",
        details={"target_outputs": program_spec_target_outputs},
    )
    _check(
        checks,
        name="wave2.program_spec.structured_path_exercised",
        passed=program_spec_source == "executor_structured",
        message="Closure exercised the structured ProgramSpec path instead of bootstrap fallback",
        wave="wave2",
        details={"program_spec_source": program_spec_source or None},
    )

    if require_closed:
        _check(
            checks,
            name="wave2.session.closed_required",
            passed=session_status == "closed",
            message="Closed session required for closure success validation",
            wave="wave2",
            details={"session_status": session_status},
        )

    landed_result = _require_json(
        trace_dir, "06_landed_result.json", checks, wave="wave2", required=False
    )
    progress_snapshot = _require_json(
        trace_dir, "07_progress_snapshot.json", checks, wave="wave2", required=False
    )
    memory_detail = _require_json(
        trace_dir, "09_memory_detail.json", checks, wave="wave2", required=False
    )
    memory_impact_graph = _require_json(
        trace_dir, "10_memory_impact_graph.json", checks, wave="wave2", required=False
    )

    if session_status == "closed":
        execution_id = _nonempty_text(summary.get("execution_id"))
        canonical_memory_item_id = (
            _nonempty_text(session_metadata.get("canonical_memory_item_id"))
            or _nonempty_text(summary.get("memory_item_id"))
        )
        memory_detail_payload = _coerce_dict(memory_detail)
        memory_item = _coerce_dict(memory_detail_payload.get("memory_item"))
        memory_detail_id = (
            _nonempty_text(memory_detail_payload.get("id"))
            or _nonempty_text(memory_item.get("id"))
        )
        _check(
            checks,
            name="wave2.closed.execution_present",
            passed=bool(execution_id),
            message="Closed session exposes execution_id for artifact/result lookup",
            wave="wave2",
            details={"execution_id": execution_id},
        )
        _check(
            checks,
            name="wave2.closed.memory_writeback_present",
            passed=event_counts.get("memory_writeback", 0) >= 1,
            message="Closed session event trace contains memory_writeback",
            wave="wave2",
            details={"event_counts": event_counts},
        )
        _check(
            checks,
            name="wave2.closed.canonical_memory_present",
            passed=bool(canonical_memory_item_id),
            message="Closed session metadata exposes canonical_memory_item_id",
            wave="wave2",
            details={"canonical_memory_item_id": canonical_memory_item_id},
        )
        _check(
            checks,
            name="wave2.closed.landed_result_present",
            passed=isinstance(landed_result, dict) and bool(landed_result),
            message="Closed session has landed execution result snapshot",
            wave="wave2",
            details={"has_landed_result": bool(landed_result)},
        )
        _check(
            checks,
            name="wave2.closed.progress_snapshot_present",
            passed=isinstance(progress_snapshot, dict) and bool(progress_snapshot),
            message="Closed session has progress snapshot artifact",
            wave="wave2",
            details={"has_progress_snapshot": bool(progress_snapshot)},
        )
        _check(
            checks,
            name="wave2.closed.memory_detail_present",
            passed=(
                isinstance(memory_detail, dict)
                and memory_detail_id == canonical_memory_item_id
            ),
            message="Closed session canonical memory detail is fetchable",
            wave="wave2",
            details={
                "memory_detail_id": memory_detail_id,
                "canonical_memory_item_id": canonical_memory_item_id,
            },
        )
        _check(
            checks,
            name="wave2.closed.memory_impact_graph_present",
            passed=isinstance(memory_impact_graph, dict) and bool(memory_impact_graph),
            message="Closed session has memory impact graph evidence",
            wave="wave2",
            details={"has_memory_impact_graph": bool(memory_impact_graph)},
        )
    else:
        _check(
            checks,
            name="wave2.failed.memory_writeback_not_required",
            passed=session_status == "failed",
            message="Failed terminal path is allowed but does not require writeback artifacts",
            wave="wave2",
            details={"session_status": session_status},
        )
        _check(
            checks,
            name="wave2.failed.environment_restart_diagnosed",
            passed=(
                (session_status != "failed")
                or (not restart_evidence_expected)
                or environment_restart["detected"]
            ),
            message="Failed session explicitly diagnoses backend restart/startup recovery when present",
            wave="wave2",
            details={
                **environment_restart,
                "restart_evidence_expected": restart_evidence_expected,
            },
        )

    last_graph = _coerce_dict(session_metadata.get("last_round_routing_graph"))
    last_warning = _coerce_dict(session_metadata.get("last_round_routing_warning"))
    prompt_summary = _coerce_dict(session_metadata.get("round_routing_prompt_mode_summary"))
    routing_present = bool(
        last_graph
        or last_warning
        or prompt_summary
        or event_counts.get("round_routing_graph", 0)
        or event_counts.get("round_routing_warning", 0)
    )

    _check(
        checks,
        name="wave3.routing.present_when_required",
        passed=(not require_dynamic_routing) or routing_present,
        message="Dynamic routing artifacts are present when required",
        wave="wave3",
        details={
            "require_dynamic_routing": require_dynamic_routing,
            "routing_present": routing_present,
        },
    )

    if routing_present or require_dynamic_routing:
        _check(
            checks,
            name="wave3.routing.graph_trace_present",
            passed=bool(last_graph) and event_counts.get("round_routing_graph", 0) >= 1,
            message="Session metadata and event trace both expose round_routing_graph",
            wave="wave3",
            details={
                "has_last_round_routing_graph": bool(last_graph),
                "round_routing_graph_events": event_counts.get("round_routing_graph", 0),
            },
        )
        _check(
            checks,
            name="wave3.routing.prompt_summary_present",
            passed=bool(prompt_summary) and (prompt_summary.get("total_decisions") or 0) >= 1,
            message="Session metadata persists prompt mode summary with decisions",
            wave="wave3",
            details={
                "has_prompt_summary": bool(prompt_summary),
                "total_decisions": prompt_summary.get("total_decisions"),
            },
        )

        routing_prompt_mode = _nonempty_text(last_graph.get("metadata", {}).get("routing_prompt_mode"))
        _check(
            checks,
            name="wave4.prompt_mode.valid",
            passed=(routing_prompt_mode in VALID_PROMPT_MODES) or bool(prompt_summary),
            message="Latest routing graph or prompt summary exposes a valid prompt mode",
            wave="wave4",
            details={"routing_prompt_mode": routing_prompt_mode},
        )
        _check(
            checks,
            name="wave4.prompt_summary.health_valid",
            passed=_nonempty_text(prompt_summary.get("health_status")) in VALID_ROUTING_HEALTH,
            message="Prompt summary health_status is in the supported routing health set",
            wave="wave4",
            details={"health_status": prompt_summary.get("health_status")},
        )
        _check(
            checks,
            name="wave4.prompt_summary.ratios_bounded",
            passed=(
                _between_zero_and_one(prompt_summary.get("fallback_ratio"))
                and _between_zero_and_one(prompt_summary.get("compressed_ratio"))
            ),
            message="Fallback and compressed ratios stay within [0, 1]",
            wave="wave4",
            details={
                "fallback_ratio": prompt_summary.get("fallback_ratio"),
                "compressed_ratio": prompt_summary.get("compressed_ratio"),
            },
        )
        if event_counts.get("round_routing_warning", 0) >= 1 or last_warning:
            _check(
                checks,
                name="wave4.warning.health_fields_present",
                passed=bool(
                    _nonempty_text(last_warning.get("routing_health_status"))
                    and _nonempty_text(last_warning.get("routing_health_reason"))
                ),
                message="Latest routing warning carries routing health fields",
                wave="wave4",
                details={
                    "routing_health_status": last_warning.get("routing_health_status"),
                    "routing_health_reason": last_warning.get("routing_health_reason"),
                },
            )

    wave_status: Dict[str, str] = {}
    for wave in ("wave2", "wave3", "wave4"):
        wave_checks = [check for check in checks if check["wave"] == wave]
        if not wave_checks:
            wave_status[wave] = "not_applicable"
            continue
        wave_status[wave] = "passed" if all(check["passed"] for check in wave_checks) else "failed"

    passed = all(check["passed"] for check in checks)
    report = {
        "trace_dir": str(trace_dir),
        "passed": passed,
        "require_closed": require_closed,
        "require_dynamic_routing": require_dynamic_routing,
        "summary": {
            "session_id": session_id,
            "session_status": session_status,
            "compile_job_id": compile_job_id,
            "compile_job_status": compile_job_status,
            "terminal_state": terminal_state,
            "program_spec_source": program_spec_source or None,
            "program_spec_workstream_count": program_spec_workstream_count,
            "program_spec_structured": program_spec_source == "executor_structured",
            "environment_restart_detected": environment_restart["detected"],
            "environment_restart_reasons": environment_restart["reasons"],
            "pipeline_failure_stage": environment_restart["pipeline_failure_stage"],
            "environment_blocker": None,
            "provider_status_check": provider_status_check or None,
            "event_counts": event_counts,
            "wave_status": wave_status,
        },
        "checks": checks,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Wave 2-4 meeting closure trace")
    parser.add_argument("--trace-dir", required=True, help="Trace directory produced by closure E2E")
    parser.add_argument(
        "--require-closed",
        action="store_true",
        help="Require session terminal status to be closed instead of accepting failed terminal truth",
    )
    parser.add_argument(
        "--require-dynamic-routing",
        action="store_true",
        help="Require dynamic routing graph/prompt-mode evidence to be present in trace artifacts",
    )
    parser.add_argument(
        "--write-report",
        help="Optional path to write the validation JSON report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_trace(
        Path(args.trace_dir),
        require_closed=args.require_closed,
        require_dynamic_routing=args.require_dynamic_routing,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False)
    print(payload)
    if args.write_report:
        _write_json(Path(args.write_report), report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
