from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "e2e"
    / "validate_meeting_wave_closure.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_meeting_wave_closure", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _build_trace_dir(
    root: Path,
    *,
    session_status: str = "closed",
    include_routing: bool = True,
    include_program_spec: bool = True,
    program_spec_source: str = "executor_structured",
    provider_status_required: bool = False,
    provider_status_available: bool = True,
    provider_status_matched: bool = True,
    nested_memory_detail: bool = False,
    pipeline_failure_stage: str | None = None,
    backend_runtime_restarted: bool = False,
    preflight_failed: bool = False,
) -> Path:
    trace_dir = root / "closure"
    trace_dir.mkdir(parents=True, exist_ok=True)

    compile_job_status = "succeeded" if session_status == "closed" else "failed"
    summary = {
        "run_id": "run-001",
        "workspace_id": "ws-001",
        "project_id": "proj-001",
        "thread_id": "thread-001",
        "compile_job_id": "job-001",
        "compile_job_status": compile_job_status,
        "session_id": "sess-001",
        "execution_id": "exec-001" if session_status == "closed" else "",
        "memory_item_id": "mem-001" if session_status == "closed" else "",
        "terminal_state": "preflight_failed" if preflight_failed else session_status,
        "trace_dir": str(trace_dir),
    }
    session_metadata = {
        "canonical_memory_item_id": "mem-001",
    }
    if include_program_spec:
        session_metadata["last_program_spec"] = {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Series Bible",
                    "description": "Draft the long-form series bible.",
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Storyboard Seeds",
                    "description": "Draft storyboard seeds for arc one.",
                    "eligible_engines": ["tool:storyboard.generate"],
                },
            ],
            "dependency_graph": {"WS2": ["WS1"]},
            "target_outputs": ["series_bible", "storyboard_seed_pack"],
            "scale": "program",
        }
        session_metadata["last_program_spec_source"] = program_spec_source
        session_metadata["last_program_spec_workstream_count"] = 2
        summary["program_spec_source"] = program_spec_source
        summary["program_spec_workstream_count"] = 2
    if pipeline_failure_stage:
        session_metadata["pipeline_failure"] = {
            "stage": pipeline_failure_stage,
            "error": "Compile job was interrupted by backend restart before completion.",
        }
    if include_routing:
        session_metadata["last_round_routing_graph"] = {
            "session_id": "sess-001",
            "round_number": 2,
            "metadata": {
                "routing_prompt_mode": "compressed_sparse",
                "routing_health_status": "warning",
                "routing_health_reason": "compression_pressure",
            },
        }
        session_metadata["last_round_routing_warning"] = {
            "warning_types": ["context_pressure"],
            "routing_health_status": "warning",
            "routing_health_reason": "compression_pressure",
        }
        session_metadata["round_routing_prompt_mode_summary"] = {
            "total_decisions": 2,
            "adaptive_count": 1,
            "adaptive_ratio": 0.5,
            "compressed_count": 1,
            "compressed_ratio": 0.5,
            "fallback_count": 0,
            "fallback_ratio": 0.0,
            "health_status": "warning",
            "health_reason": "compression_pressure",
            "last_prompt_mode": "compressed_sparse",
            "last_role_id": "executor",
            "last_reason": "context_pressure",
        }

    events = [
        {"event_type": "meeting_end"},
    ]
    if session_status == "closed":
        events.extend(
            [
                {"event_type": "memory_writeback"},
                {"event_type": "action_item"},
            ]
        )
    if include_routing:
        events.extend(
            [
                {"event_type": "round_routing_graph"},
                {"event_type": "round_routing_warning"},
            ]
        )

    _write_json(
        trace_dir / "00_provider_status_check.json",
        {
            "available": provider_status_available,
            "matched": provider_status_matched,
            "required": provider_status_required,
            "managed_bridge_mode": False,
            "workspace_id": "ws-001",
            "expected_client_id": "e2e-codex-run-001",
            "reason": (
                "workspace_codex_cli_authenticated"
                if provider_status_matched
                else "workspace_codex_cli_not_observed"
            ),
        },
    )
    if not preflight_failed:
        _write_json(
            trace_dir / "02_compile_response.json",
            {
                "http_status": 202,
                "curl_exit": 0,
                "timeout_seconds": 240,
                "headers_raw": "HTTP/1.1 202 Accepted",
                "body_raw": json.dumps(
                    {
                        "compile_job_id": "job-001",
                        "job_id": "job-001",
                        "session_id": "sess-001",
                    }
                ),
            },
        )
        _write_json(
            trace_dir / "02a_compile_acceptance.json",
            {"compile_job_id": "job-001", "session_id": "sess-001"},
        )
        _write_json(
            trace_dir / "02c_compile_job.json",
            {
                "id": "job-001",
                "status": compile_job_status,
                "session_id": "sess-001",
            },
        )
        _write_json(
            trace_dir / "03_session_after_close.json",
            {
                "id": "sess-001",
                "status": session_status,
                "action_items": (
                    [{"execution_id": "exec-001", "title": "Ship partner brief"}]
                    if session_status == "closed"
                    else []
                ),
                "metadata": session_metadata,
            },
        )
        _write_json(
            trace_dir / "04_session_events.json",
            {
                "session_id": "sess-001",
                "workspace_id": "ws-001",
                "events": events,
                "total": len(events),
            },
        )
    if backend_runtime_restarted:
        _write_json(
            trace_dir / "00_backend_runtime_before.json",
            {
                "available": True,
                "container_name": "mindscape-ai-local-core-backend",
                "container_id": "container-001",
                "started_at": "2026-03-31T07:05:00+00:00",
                "status": "running",
                "running": True,
            },
        )
        _write_json(
            trace_dir / "11_backend_runtime_after.json",
            {
                "available": True,
                "container_name": "mindscape-ai-local-core-backend",
                "container_id": "container-001",
                "started_at": "2026-03-31T07:09:00+00:00",
                "status": "running",
                "running": True,
            },
        )
    if session_status == "closed":
        _write_json(trace_dir / "06_landed_result.json", {"execution_id": "exec-001"})
        _write_json(trace_dir / "07_progress_snapshot.json", {"progress": {"percent": 100}})
        _write_json(
            trace_dir / "09_memory_detail.json",
            {"memory_item": {"id": "mem-001"}} if nested_memory_detail else {"id": "mem-001"},
        )
        _write_json(trace_dir / "10_memory_impact_graph.json", {"nodes": [], "edges": []})
    _write_json(trace_dir / "summary.json", summary)
    return trace_dir


def test_validate_trace_passes_for_closed_success_with_dynamic_routing(tmp_path: Path):
    trace_dir = _build_trace_dir(tmp_path, session_status="closed", include_routing=True)

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is True
    assert report["summary"]["wave_status"]["wave2"] == "passed"
    assert report["summary"]["wave_status"]["wave3"] == "passed"
    assert report["summary"]["wave_status"]["wave4"] == "passed"


def test_validate_trace_fails_when_dynamic_routing_is_required_but_missing(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(tmp_path, session_status="closed", include_routing=False)

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is False
    failed_checks = [check for check in report["checks"] if not check["passed"]]
    assert any(
        check["name"] == "wave3.routing.present_when_required"
        for check in failed_checks
    )


def test_validate_trace_accepts_failed_terminal_truth_when_closed_not_required(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(tmp_path, session_status="failed", include_routing=False)

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=False,
        require_dynamic_routing=False,
    )

    assert report["passed"] is True
    assert report["summary"]["session_status"] == "failed"
    assert report["summary"]["compile_job_status"] == "failed"


def test_validate_trace_diagnoses_environment_restart_for_failed_terminal_truth(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="failed",
        include_routing=True,
        pipeline_failure_stage="startup_recovery",
        backend_runtime_restarted=True,
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is False
    assert report["summary"]["environment_restart_detected"] is True
    assert "startup_recovery" in report["summary"]["environment_restart_reasons"]
    restart_check = next(
        check
        for check in report["checks"]
        if check["name"] == "wave2.failed.environment_restart_diagnosed"
    )
    assert restart_check["passed"] is True


def test_validate_trace_accepts_advisory_provider_status_probe_when_unmatched(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="closed",
        include_routing=False,
        provider_status_required=False,
        provider_status_available=False,
        provider_status_matched=False,
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=False,
    )

    assert report["passed"] is True
    assert report["summary"]["provider_status_check"]["required"] is False
    provider_check = next(
        check
        for check in report["checks"]
        if check["name"] == "wave2.environment.provider_status_requirement"
    )
    assert provider_check["passed"] is True


def test_validate_trace_reports_workspace_codex_preflight_blocker(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="failed",
        include_routing=False,
        provider_status_required=False,
        provider_status_available=True,
        provider_status_matched=False,
        preflight_failed=True,
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is False
    assert report["summary"]["terminal_state"] == "preflight_failed"
    assert report["summary"]["environment_blocker"] == "workspace_codex_cli_not_observed"
    blocker_check = next(
        check
        for check in report["checks"]
        if check["name"] == "wave2.environment.workspace_codex_cli_ready"
    )
    assert blocker_check["passed"] is False


def test_validate_trace_accepts_nested_memory_detail_payload(tmp_path: Path):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="closed",
        include_routing=True,
        nested_memory_detail=True,
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is True
    memory_detail_check = next(
        check
        for check in report["checks"]
        if check["name"] == "wave2.closed.memory_detail_present"
    )
    assert memory_detail_check["passed"] is True


def test_validate_trace_fails_when_program_spec_is_missing(tmp_path: Path):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="closed",
        include_routing=True,
        include_program_spec=False,
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is False
    failed_checks = [check for check in report["checks"] if not check["passed"]]
    assert any(
        check["name"] == "wave2.program_spec.present"
        for check in failed_checks
    )


def test_validate_trace_fails_when_only_bootstrap_program_spec_was_exercised(
    tmp_path: Path,
):
    trace_dir = _build_trace_dir(
        tmp_path,
        session_status="closed",
        include_routing=True,
        include_program_spec=True,
        program_spec_source="action_intent_bootstrap",
    )

    report = MODULE.validate_trace(
        trace_dir,
        require_closed=True,
        require_dynamic_routing=True,
    )

    assert report["passed"] is False
    structured_check = next(
        check
        for check in report["checks"]
        if check["name"] == "wave2.program_spec.structured_path_exercised"
    )
    assert structured_check["passed"] is False
