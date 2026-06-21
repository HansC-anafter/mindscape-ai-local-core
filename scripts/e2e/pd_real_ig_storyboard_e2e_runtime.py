"""Runtime orchestration for the PD real IG storyboard E2E."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from pd_real_ig_storyboard_e2e_core import DEFAULT_REFS, _utc_stamp, _write_json
from pd_real_ig_storyboard_e2e_http import (
    _fetch_session_and_events,
    _http_json,
    _submit_command_with_recovery_marker,
)
from pd_real_ig_storyboard_e2e_payloads import _build_envelope, _build_start_body
from pd_real_ig_storyboard_e2e_validation import (
    _collect_existing_paths,
    _copy_artifacts,
    _quota_evidence_summary,
    _validate,
)


def _run_quota_preflight(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    if args.skip_quota_preflight:
        return {"status": "skipped"}
    script = Path(__file__).with_name("codex_pool_quota_preflight.py")
    cmd = [
        sys.executable,
        str(script),
        "--workspace-id",
        args.workspace_id,
        "--max-runtime-probes",
        str(args.codex_quota_max_runtime_probes),
        "--timeout-seconds",
        str(args.codex_quota_timeout_seconds),
        "--stall-timeout-seconds",
        str(args.codex_quota_stall_timeout_seconds),
        "--target-successes",
        str(args.codex_quota_target_successes),
    ]
    if args.required_codex_login_email:
        cmd.extend(
            [
                "--required-login-email",
                args.required_codex_login_email,
            ]
        )
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    (output_dir / "quota_preflight.stdout.txt").write_text(completed.stdout)
    (output_dir / "quota_preflight.stderr.txt").write_text(completed.stderr)
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        parsed = {
            "status": "failed",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
    successful_scope_count = int(parsed.get("successful_quota_scope_count") or 0)
    flags_supported = parsed.get("required_flags_supported")
    required_flags_passed = isinstance(flags_supported, dict) and all(
        bool(value) for value in flags_supported.values()
    )
    hard_gate_passed = (
        completed.returncode == 0
        and parsed.get("status") == "available"
        and successful_scope_count >= int(args.codex_quota_target_successes)
        and bool(parsed.get("codex_cli_version"))
        and required_flags_passed
    )
    parsed["hard_gate_target_successes"] = int(args.codex_quota_target_successes)
    if not hard_gate_passed:
        parsed.setdefault("status", "failed")
        parsed["hard_gate_passed"] = False
        _write_json(output_dir / "quota_preflight.json", parsed)
        return parsed
    parsed["hard_gate_passed"] = True
    _write_json(output_dir / "quota_preflight.json", parsed)
    return parsed


def run_e2e(
    args: argparse.Namespace,
    *,
    http_json: Callable[..., Any] = _http_json,
    quota_preflight: Callable[[argparse.Namespace, Path], dict[str, Any]] = _run_quota_preflight,
) -> dict[str, Any]:
    run_id = args.run_id or f"E2E-PD-REAL-IG-{_utc_stamp()}"
    output_dir = Path(args.output_dir or f".tmp/pd-e2e-real-ig-{run_id.lower()}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_ids = [item.strip() for item in args.reference_ids.split(",") if item.strip()]
    if not ref_ids:
        ref_ids = list(DEFAULT_REFS)

    quota = quota_preflight(args, output_dir)
    runtime_pool_evidence = _quota_evidence_summary(quota)
    if quota.get("status") != "available" or not bool(quota.get("hard_gate_passed")):
        result = {
            "status": "blocked",
            "run_id": run_id,
            "output_dir": str(output_dir),
            "workspace_id": args.workspace_id,
            "hard_gate": "codex_quota_preflight",
            "quota_preflight": quota,
            "runtime_pool_evidence": runtime_pool_evidence,
            "codex_cli_version": quota.get("codex_cli_version"),
            "validation": {
                "passed": False,
                "failures": ["codex_quota_preflight_blocked"],
            },
        }
        _write_json(output_dir / "result.json", result)
        return result

    start_body = _build_start_body(args, run_id)
    _write_json(output_dir / "start_body.json", start_body)
    start_url = (
        f"{args.api_url.rstrip('/')}/api/v1/workspaces/{args.workspace_id}/meeting-sessions/start"
    )
    start_response = http_json("POST", start_url, start_body, timeout=args.http_timeout_seconds)
    _write_json(output_dir / "start_response.json", start_response)
    meeting_id = str(start_response.get("id") or "").strip()
    if not meeting_id:
        raise RuntimeError("Meeting start response did not include id")

    command_id = args.command_id or f"cmd_{run_id.lower()}_storyboard_gen"
    envelope = _build_envelope(
        args,
        meeting_id=meeting_id,
        run_id=run_id,
        command_id=command_id,
        ref_ids=ref_ids,
    )
    _write_json(output_dir / "envelope.json", envelope)
    submit_url = (
        f"{args.api_url.rstrip('/')}/api/v1/workspaces/{args.workspace_id}/meetings/{meeting_id}/commands"
    )
    session_url = (
        f"{args.api_url.rstrip('/')}/api/v1/workspaces/{args.workspace_id}/meeting-sessions/{meeting_id}"
    )
    events_url = f"{session_url}/events?limit=2000"
    submit_response, submit_transport_error = _submit_command_with_recovery_marker(
        args=args,
        submit_url=submit_url,
        envelope=envelope,
        meeting_id=meeting_id,
        command_id=command_id,
        http_json=http_json,
    )
    _write_json(output_dir / "submit_response.json", submit_response)
    session_response, events_response, post_command_recovery = _fetch_session_and_events(
        args=args,
        session_url=session_url,
        events_url=events_url,
        meeting_id=meeting_id,
        command_id=command_id,
        poll_until_terminal=submit_transport_error,
        http_json=http_json,
    )
    _write_json(output_dir / "meeting_session.json", session_response)
    _write_json(output_dir / "meeting_events.json", events_response)
    _write_json(output_dir / "post_command_recovery.json", post_command_recovery)

    payloads = [quota, start_response, submit_response, session_response, events_response]
    artifact_paths = _collect_existing_paths(submit_response)
    artifact_paths.extend(_collect_existing_paths(session_response))
    artifact_paths.extend(_collect_existing_paths(events_response))
    collected = _copy_artifacts(artifact_paths, output_dir)
    validation = _validate(args=args, payloads=payloads, collected_paths=collected)
    _write_json(output_dir / "validation_report.json", validation)

    result = {
        "status": "passed" if validation["passed"] else "failed",
        "run_id": run_id,
        "output_dir": str(output_dir),
        "workspace_id": args.workspace_id,
        "meeting_id": meeting_id,
        "command_id": command_id,
        "submit_transport_error": submit_response if submit_transport_error else None,
        "post_command_recovery": post_command_recovery,
        "quota_preflight": quota,
        "runtime_pool_evidence": runtime_pool_evidence,
        "codex_cli_version": quota.get("codex_cli_version"),
        "validation": validation,
    }
    _write_json(output_dir / "result.json", result)
    return result
