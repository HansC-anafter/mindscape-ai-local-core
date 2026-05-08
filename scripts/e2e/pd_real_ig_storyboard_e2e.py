#!/usr/bin/env python3
"""Run the real IG reference PD storyboard E2E and validate content gates."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REFS = [
    "ref_63601788",
    "ref_8849fff0",
    "ref_50eb8376",
    "ref_6702844a",
    "ref_c3f6a15d",
    "ref_9ddb375f",
    "ref_21f1b00a",
    "ref_23953361",
]

_TRANSPORT_EXCEPTIONS = (
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    http.client.BadStatusLine,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    socket.timeout,
    urllib.error.URLError,
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 1200) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def _request_error_payload(
    exc: BaseException,
    *,
    method: str,
    url: str,
    meeting_id: str = "",
    command_id: str = "",
    context: str = "http_request",
) -> dict[str, Any]:
    reason = getattr(exc, "reason", None)
    return {
        "status": "transport_error",
        "context": context,
        "method": method,
        "url": url,
        "meeting_id": meeting_id,
        "command_id": command_id,
        "error_type": exc.__class__.__name__,
        "error": str(reason or exc),
        "resumable_after_transport_error": True,
    }


def _submit_command_with_recovery_marker(
    *,
    args: argparse.Namespace,
    submit_url: str,
    envelope: dict[str, Any],
    meeting_id: str,
    command_id: str,
) -> tuple[dict[str, Any], bool]:
    try:
        response = _http_json(
            "POST",
            submit_url,
            envelope,
            timeout=args.command_timeout_seconds + 60,
        )
        return _as_dict(response), False
    except _TRANSPORT_EXCEPTIONS as exc:
        return (
            _request_error_payload(
                exc,
                method="POST",
                url=submit_url,
                meeting_id=meeting_id,
                command_id=command_id,
                context="command_submit",
            ),
            True,
        )


def _session_is_terminal(session_response: Any) -> bool:
    session = _as_dict(session_response)
    status = str(session.get("status") or "").strip().lower()
    return bool(session.get("ended_at")) or status in {
        "closed",
        "completed",
        "complete",
        "failed",
        "cancelled",
        "canceled",
        "ended",
    }


def _safe_fetch_json(
    *,
    method: str,
    url: str,
    timeout: int,
    meeting_id: str,
    command_id: str,
    context: str,
) -> dict[str, Any]:
    try:
        return _as_dict(_http_json(method, url, timeout=timeout))
    except _TRANSPORT_EXCEPTIONS as exc:
        return _request_error_payload(
            exc,
            method=method,
            url=url,
            meeting_id=meeting_id,
            command_id=command_id,
            context=context,
        )


def _fetch_session_and_events(
    *,
    args: argparse.Namespace,
    session_url: str,
    events_url: str,
    meeting_id: str,
    command_id: str,
    poll_until_terminal: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + max(0, int(args.post_command_poll_seconds))
    interval = max(0.0, float(args.post_command_poll_interval_seconds))
    attempts = 0
    session_response: dict[str, Any] = {}
    events_response: dict[str, Any] = {}
    terminal = False

    while True:
        attempts += 1
        session_response = _safe_fetch_json(
            method="GET",
            url=session_url,
            timeout=args.http_timeout_seconds,
            meeting_id=meeting_id,
            command_id=command_id,
            context="meeting_session_fetch",
        )
        events_response = _safe_fetch_json(
            method="GET",
            url=events_url,
            timeout=args.http_timeout_seconds,
            meeting_id=meeting_id,
            command_id=command_id,
            context="meeting_events_fetch",
        )
        terminal = _session_is_terminal(session_response)
        if terminal or not poll_until_terminal or time.monotonic() >= deadline:
            break
        if interval:
            time.sleep(interval)

    recovery = {
        "poll_until_terminal": poll_until_terminal,
        "poll_attempts": attempts,
        "session_terminal": terminal,
        "session_status": session_response.get("status"),
        "session_ended_at": session_response.get("ended_at"),
    }
    return session_response, events_response, recovery


def _build_start_body(args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    return {
        "workspace_id": args.workspace_id,
        "project_id": args.project_id,
        "thread_id": args.thread_id or f"thread_e2e_pd_real_ig_{run_id.lower()}",
        "lens_id": args.lens_id,
        "meeting_type": "e2e_validation",
        "agenda": [
            "Run PD real IG 90s storyboard E2E with workspace codex_cli, IG reference validation, and content gate evidence"
        ],
        "success_criteria": [
            "workspace codex_cli bridge connected",
            "IG refs validation checklist passes",
            "45 numbered scenes",
            "total duration about 90 seconds",
            "source-backed IG reference cue map",
            "per-scene runtime LLM judge pass",
            "no internal workflow copy",
            "storyboard assets collected in one directory",
        ],
        "max_rounds": args.max_rounds,
    }


def _quality_requirements(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "rewrite_until_quality_passed": True,
        "reference_grounding_required": True,
        "audience_facing_script_required": True,
        "reject_vague_scene_copy": True,
        "per_scene_content_specificity": "high",
        "deliverable_stage": "storyboard_review",
        "creative_objective": "source_backed_vertical_reels_storyboard",
        "originality_required": True,
        "human_review_required_before_publish": True,
        "target": {
            "deliverable_kind": "90s_reels_storyboard",
            "scene_count_target": args.scene_count_target,
            "scene_count_floor": args.scene_count_floor,
            "total_duration_sec": args.target_duration_sec,
            "scene_count": args.scene_count_target,
            "min_scene_count": args.scene_count_floor,
            "duration_sec": args.target_duration_sec,
            "visual_scope": "storyboard_frames",
            "target_platform": "instagram_reels",
        },
        "content_quality": {
            "require_reference_grounding": True,
            "require_concrete_scene_copy": True,
            "require_per_scene_judge": True,
            "reject_internal_workflow_copy": True,
            "reject_generic_filler": True,
        },
        "visual_quality": {
            "require_storyboard_frames": True,
            "require_contact_sheet": True,
        },
    }


def _build_envelope(
    args: argparse.Namespace,
    *,
    meeting_id: str,
    run_id: str,
    command_id: str,
    ref_ids: list[str],
) -> dict[str, Any]:
    human_instructions = (
        "Create a source-backed 90 second vertical Instagram Reels storyboard from "
        "the selected rin.215_ IG references. Produce 45 numbered scenes at about "
        "2 seconds per scene, with concrete shot-by-shot visual action, screen text, "
        "voiceover, reference grounding, pacing, brand tone, and CTA logic. Do not "
        "use synthetic references or internal workflow copy."
    )
    quality_requirements = _quality_requirements(args)
    input_params = {
        "project_id": args.project_id,
        "source_type": "generative",
        "selected_reference_ids": ref_ids,
        "reference_ids": ref_ids,
        "target_duration_sec": args.target_duration_sec,
        "scene_count_target": args.scene_count_target,
        "scene_count_floor": args.scene_count_floor,
        "raw_intent_text": human_instructions,
        "e2e_run_id": run_id,
        "quality_requirements": quality_requirements,
        "human_instructions": human_instructions,
    }
    return {
        "workspace_id": args.workspace_id,
        "meeting_id": meeting_id,
        "command_id": command_id,
        "origin_surface": "meeting_workbench",
        "actor": "user",
        "intent_text": human_instructions,
        "context_objects": [
            {
                "role": "source",
                "ref": {
                    "uri": f"mindscape://ig/reference/{ref_id}",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": ref_id,
                    "workspace_id": args.workspace_id,
                },
            }
            for ref_id in ref_ids
        ],
        "requested_action": {
            "verb": "execute_playbook",
            "pack_code": "performance_direction",
            "playbook_code": "pd_storyboard_gen",
            "parameters": dict(input_params),
        },
        "expected_outputs": [
            "pd_storyboard_manifest",
            "pd_reference_cue_map",
            "pd_storyboard_quality_gate",
            "pd_storyboard_scene_judge",
            "pd_storyboard_instruction_contract",
            "pd_storyboard_contact_sheet",
        ],
        "write_mode": "proposal_only",
        "metadata": {
            "dispatch_mode": "route_meeting_orchestration",
            "force_playbook_request": False,
            "explicit_override": False,
            "meeting_orchestration_timeout_seconds": args.command_timeout_seconds,
            "raw_intent_text": human_instructions,
            "selected_reference_ids": ref_ids,
            "e2e_run_id": run_id,
            "quality_requirements": quality_requirements,
            "action_parameters": {
                "project_id": args.project_id,
                "source_type": "generative",
                "selected_reference_ids": ref_ids,
                "reference_ids": ref_ids,
                "target_duration_sec": args.target_duration_sec,
                "scene_count_target": args.scene_count_target,
                "scene_count_floor": args.scene_count_floor,
                "e2e_run_id": run_id,
            },
        },
        "thread_id": args.thread_id or f"thread_e2e_pd_real_ig_{run_id.lower()}",
    }


def _iter_nodes(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nodes(child)


def _text_blob(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _find_storyboards(payloads: list[Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        for node in _iter_nodes(payload):
            if isinstance(node, dict) and isinstance(node.get("scenes"), list):
                if node.get("scenes"):
                    candidates.append(node)
            if (
                isinstance(node, dict)
                and isinstance(node.get("storyboard"), dict)
                and isinstance(node["storyboard"].get("scenes"), list)
                and node["storyboard"].get("scenes")
            ):
                candidates.append(node["storyboard"])
    candidates.sort(key=lambda item: len(item.get("scenes") or []), reverse=True)
    return candidates


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _schema_payloads(payloads: list[Any], schema_version: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for payload in payloads:
        for node in _iter_nodes(payload):
            if not isinstance(node, dict):
                continue
            if str(node.get("schema_version") or "").strip() == schema_version:
                matches.append(node)
    return matches


def _find_quality_gate_summaries(payloads: list[Any]) -> list[dict[str, Any]]:
    return _schema_payloads(payloads, "pd_storyboard_quality_gate_summary.v1")


def _find_reference_cue_maps(payloads: list[Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        for node in _iter_nodes(payload):
            if (
                isinstance(node, dict)
                and isinstance(node.get("source_reference_ids"), list)
                and isinstance(node.get("reference_cues"), list)
            ):
                candidates.append(node)
    candidates.sort(key=lambda item: len(item.get("reference_cues") or []), reverse=True)
    return candidates


def _duration_sum(scenes: list[dict[str, Any]]) -> float:
    total = 0.0
    for scene in scenes:
        for key in ("duration_sec", "duration_seconds", "seconds"):
            try:
                total += float(scene.get(key) or 0)
                break
            except (TypeError, ValueError):
                continue
    return total


def _scene_has_any(scene: dict[str, Any], needles: tuple[str, ...]) -> bool:
    blob = _text_blob(scene).lower()
    return any(needle in blob for needle in needles)


def _find_scene_judges(payloads: list[Any]) -> list[dict[str, Any]]:
    reports = _schema_payloads(payloads, "pd_storyboard_scene_judge_report.v1")
    if reports:
        reports.sort(key=lambda item: len(item.get("scene_scores") or []), reverse=True)
        return reports
    reports = []
    for payload in payloads:
        for node in _iter_nodes(payload):
            if not isinstance(node, dict):
                continue
            joined_keys = " ".join(str(key).lower() for key in node.keys())
            if "judge" in joined_keys and ("scene" in joined_keys or "storyboard" in joined_keys):
                reports.append(node)
    return reports


def _scene_id(scene: dict[str, Any], index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"sc{index:02d}").strip()


def _scene_score_id(score: dict[str, Any]) -> str:
    return str(score.get("scene_id") or score.get("id") or "").strip()


def _score_axis_passed(value: Any) -> bool:
    if value is True:
        return True
    normalized = str(value or "").strip().lower()
    return normalized in {"true", "pass", "passed", "ok", "not_applicable"}


def _runtime_evidence_uses_codex_workspace(runtime_evidence: dict[str, Any]) -> bool:
    route_mode = str(runtime_evidence.get("route_mode") or "").strip().lower()
    route_modes = {
        str(item or "").strip().lower()
        for item in _as_list(runtime_evidence.get("route_modes"))
        if str(item or "").strip()
    }
    executor_runtime = str(runtime_evidence.get("executor_runtime") or "").strip().lower()
    executor_runtimes = {
        str(item or "").strip().lower()
        for item in _as_list(runtime_evidence.get("executor_runtimes"))
        if str(item or "").strip()
    }
    workspace_runtime = (
        route_mode == "workspace_runtime"
        or route_modes == {"workspace_runtime"}
        or bool(runtime_evidence.get("all_scenes_workspace_runtime"))
    )
    codex_runtime = executor_runtime == "codex_cli" or "codex_cli" in executor_runtimes
    return workspace_runtime and codex_runtime


def _runtime_evidence_mentions_managed_provider(runtime_evidence: dict[str, Any]) -> bool:
    return "managed_provider" in _text_blob(runtime_evidence).lower()


def _collect_existing_paths(payload: Any) -> list[Path]:
    paths: list[Path] = []
    for node in _iter_nodes(payload):
        if isinstance(node, str) and (node.startswith("/") or node.startswith("~")):
            candidate = Path(os.path.expanduser(node))
            if candidate.exists() and candidate.is_file():
                paths.append(candidate)
    unique: dict[str, Path] = {}
    for path in paths:
        unique[str(path)] = path
    return list(unique.values())


def _copy_artifacts(paths: list[Path], output_dir: Path) -> list[str]:
    copied: list[str] = []
    artifact_dir = output_dir / "collected_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = artifact_dir / path.name
        if target.exists():
            target = artifact_dir / f"{path.stem}_{abs(hash(str(path))) & 0xffff:x}{path.suffix}"
        shutil.copy2(path, target)
        copied.append(str(target))
    return copied


def _quota_evidence_summary(quota: dict[str, Any]) -> dict[str, Any]:
    attempts = quota.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
    selected_attempt = next(
        (attempt for attempt in attempts if str(attempt.get("status") or "") == "available"),
        attempts[-1] if attempts else {},
    )
    identity = (
        selected_attempt.get("runtime_account_identity")
        if isinstance(selected_attempt, dict)
        else {}
    )
    if not isinstance(identity, dict):
        identity = {}
    return {
        "target_successes": quota.get("target_successes"),
        "successful_quota_scope_count": quota.get("successful_quota_scope_count"),
        "successful_quota_scope_keys": quota.get("successful_quota_scope_keys") or [],
        "successful_runtime_ids": quota.get("successful_runtime_ids") or [],
        "selected_runtime_id": (
            selected_attempt.get("selected_runtime_id") or quota.get("selected_runtime_id")
            if isinstance(selected_attempt, dict)
            else quota.get("selected_runtime_id")
        ),
        "login_email": identity.get("login_email"),
        "quota_scope_key": (
            selected_attempt.get("quota_scope_key") or quota.get("quota_scope_key")
            if isinstance(selected_attempt, dict)
            else quota.get("quota_scope_key")
        ),
        "host_session_env_class": (
            selected_attempt.get("host_session_env_class")
            if isinstance(selected_attempt, dict)
            else None
        ),
        "codex_cli_version": quota.get("codex_cli_version"),
        "required_flags_supported": quota.get("required_flags_supported"),
    }


def _validate(
    *,
    args: argparse.Namespace,
    payloads: list[Any],
    collected_paths: list[str],
) -> dict[str, Any]:
    storyboards = _find_storyboards(payloads)
    storyboard = storyboards[0] if storyboards else {}
    scenes = list(storyboard.get("scenes") or []) if storyboard else []
    scene_ids = [_scene_id(scene, index) for index, scene in enumerate(scenes, start=1)]
    duration_total = _duration_sum(scenes)
    scene_judges = _find_scene_judges(payloads)
    quality_gate_summaries = _find_quality_gate_summaries(payloads)
    quality_gate_summary = quality_gate_summaries[0] if quality_gate_summaries else {}
    reference_cue_maps = _find_reference_cue_maps(payloads)
    reference_cue_map = reference_cue_maps[0] if reference_cue_maps else {}
    failures: list[str] = []
    if len(scenes) < args.scene_count_floor:
        failures.append(f"scene_count_below_floor:{len(scenes)}<{args.scene_count_floor}")
    if len(scenes) != args.scene_count_target:
        failures.append(f"scene_count_not_target:{len(scenes)}!={args.scene_count_target}")
    if duration_total and abs(duration_total - args.target_duration_sec) > args.duration_tolerance_sec:
        failures.append(
            f"duration_out_of_tolerance:{duration_total:.2f}!~{args.target_duration_sec}"
        )
    if not duration_total:
        failures.append("duration_missing")

    scene_failures: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        missing: list[str] = []
        if not _scene_has_any(scene, ("ref_", "reference", "cue", "grounding")):
            missing.append("reference_grounding")
        if not _scene_has_any(scene, ("shot", "camera", "frame", "composition", "visual")):
            missing.append("shot_language")
        if not _scene_has_any(scene, ("voiceover", "vo", "screen text", "caption", "text")):
            missing.append("audience_copy")
        if _scene_has_any(scene, ("workflow", "internal", "implementation", "gate checklist")):
            missing.append("internal_workflow_copy")
        if missing:
            scene_failures.append(
                {
                    "scene_index": index,
                    "scene_id": scene.get("scene_id") or scene.get("id"),
                    "missing": missing,
                }
            )
    if scene_failures:
        failures.append(f"scene_contract_failures:{len(scene_failures)}")
    if not reference_cue_map:
        failures.append("reference_cue_map_missing")
    else:
        source_refs = {
            str(item or "").strip()
            for item in _as_list(reference_cue_map.get("source_reference_ids"))
            if str(item or "").strip()
        }
        required_refs = {
            item.strip()
            for item in args.reference_ids.split(",")
            if item.strip()
        }
        missing_refs = sorted(required_refs - source_refs)
        if missing_refs:
            failures.append(f"reference_cue_map_missing_selected_refs:{','.join(missing_refs)}")
        if not reference_cue_map.get("reference_cues"):
            failures.append("reference_cues_missing")
        if reference_cue_map.get("missing_reference_analysis"):
            failures.append("reference_analysis_missing")
    if not quality_gate_summary:
        failures.append("quality_gate_summary_missing")
    else:
        if not bool(quality_gate_summary.get("strict_acceptance_required")):
            failures.append("quality_gate_strict_acceptance_not_required")
        if not bool(quality_gate_summary.get("storyboard_content_high_quality_pass")):
            failures.append("quality_gate_content_high_quality_false")
        failed_gate_ids = [
            str(item or "").strip()
            for item in _as_list(quality_gate_summary.get("failed_gate_ids"))
            if str(item or "").strip()
        ]
        if failed_gate_ids:
            failures.append(f"quality_gate_failed_gate_ids:{','.join(failed_gate_ids)}")
        false_gate_ids = [
            str(gate.get("gate_id") or "unknown").strip()
            for gate in (_as_dict(gate) for gate in _as_list(quality_gate_summary.get("gates")))
            if not bool(gate.get("passed"))
        ]
        if false_gate_ids:
            failures.append(f"quality_gate_false_gates:{','.join(false_gate_ids)}")
        false_check_items: list[str] = []
        for gate in (_as_dict(gate) for gate in _as_list(quality_gate_summary.get("gates"))):
            gate_id = str(gate.get("gate_id") or "unknown").strip()
            for item in (_as_dict(item) for item in _as_list(gate.get("checklist"))):
                if not bool(item.get("passed")):
                    false_check_items.append(f"{gate_id}.{item.get('item_id') or 'unknown'}")
        if false_check_items:
            failures.append(f"quality_gate_false_checklist_items:{','.join(false_check_items[:12])}")
    selected_scene_judge = _as_dict(
        quality_gate_summary.get("scene_judge_report")
    ) or (scene_judges[0] if scene_judges else {})
    if not selected_scene_judge:
        failures.append("scene_judge_report_missing")
    else:
        judge_status = str(selected_scene_judge.get("llm_review_status") or "").strip()
        if judge_status not in {"completed", "completed_per_scene"}:
            failures.append(f"scene_judge_status_not_completed:{judge_status or 'missing'}")
        if not bool(selected_scene_judge.get("passed")):
            failures.append("scene_judge_passed_false")
        for key in ("invalid_schema", "refusal", "timeout", "max_token_truncation"):
            if bool(selected_scene_judge.get(key)):
                failures.append(f"scene_judge_{key}_true")
        scene_scores = [_as_dict(score) for score in _as_list(selected_scene_judge.get("scene_scores"))]
        if len(scene_scores) != len(scenes):
            failures.append(f"scene_judge_score_count_mismatch:{len(scene_scores)}!={len(scenes)}")
        score_ids = {_scene_score_id(score) for score in scene_scores if _scene_score_id(score)}
        missing_score_ids = sorted(set(scene_ids) - score_ids)
        if missing_score_ids:
            failures.append(f"scene_judge_missing_scene_scores:{','.join(missing_score_ids[:12])}")
        failed_axis_scores: list[str] = []
        for score in scene_scores:
            score_id = _scene_score_id(score) or "unknown"
            for axis in (
                "narrative_logic",
                "pacing",
                "visual_language",
                "reference_grounding",
                "brand_tone",
            ):
                if not _score_axis_passed(score.get(axis)):
                    failed_axis_scores.append(f"{score_id}.{axis}")
            cta_fit = score.get("cta_fit")
            cta_reason = str(score.get("cta_not_applicable_reason") or "").strip()
            if not _score_axis_passed(cta_fit) or (
                str(cta_fit or "").strip().lower() == "not_applicable" and not cta_reason
            ):
                failed_axis_scores.append(f"{score_id}.cta_fit")
        if failed_axis_scores:
            failures.append(f"scene_judge_axis_failures:{','.join(failed_axis_scores[:12])}")
        runtime_evidence = _as_dict(selected_scene_judge.get("runtime_evidence"))
        if not runtime_evidence:
            failures.append("scene_judge_runtime_evidence_missing")
        elif not _runtime_evidence_uses_codex_workspace(runtime_evidence):
            failures.append("scene_judge_runtime_not_workspace_codex")
        if runtime_evidence and _runtime_evidence_mentions_managed_provider(runtime_evidence):
            failures.append("scene_judge_runtime_mentions_managed_provider")
    if not collected_paths:
        failures.append("collected_artifacts_missing")

    return {
        "passed": not failures,
        "failures": failures,
        "scene_count": len(scenes),
        "target_scene_count": args.scene_count_target,
        "scene_count_floor": args.scene_count_floor,
        "duration_total_sec": duration_total,
        "target_duration_sec": args.target_duration_sec,
        "duration_tolerance_sec": args.duration_tolerance_sec,
        "scene_judge_report_count": len(scene_judges),
        "quality_gate_summary_count": len(quality_gate_summaries),
        "quality_gate_failed_gate_ids": (
            quality_gate_summary.get("failed_gate_ids") if quality_gate_summary else []
        ),
        "selected_scene_judge_status": (
            selected_scene_judge.get("llm_review_status") if selected_scene_judge else None
        ),
        "selected_scene_judge_passed": (
            selected_scene_judge.get("passed") if selected_scene_judge else None
        ),
        "reference_cue_map_count": len(reference_cue_maps),
        "reference_cue_count": len(reference_cue_map.get("reference_cues") or [])
        if reference_cue_map
        else 0,
        "scene_failures": scene_failures[:20],
        "storyboard_keys": sorted(storyboard.keys()) if storyboard else [],
        "collected_artifacts": collected_paths,
    }


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


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or f"E2E-PD-REAL-IG-{_utc_stamp()}"
    output_dir = Path(args.output_dir or f".tmp/pd-e2e-real-ig-{run_id.lower()}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_ids = [item.strip() for item in args.reference_ids.split(",") if item.strip()]
    if not ref_ids:
        ref_ids = list(DEFAULT_REFS)

    quota = _run_quota_preflight(args, output_dir)
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
    start_response = _http_json("POST", start_url, start_body, timeout=args.http_timeout_seconds)
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
    )
    _write_json(output_dir / "submit_response.json", submit_response)
    session_response, events_response, post_command_recovery = _fetch_session_and_events(
        args=args,
        session_url=session_url,
        events_url=events_url,
        meeting_id=meeting_id,
        command_id=command_id,
        poll_until_terminal=submit_transport_error,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8200")
    parser.add_argument("--workspace-id", default="bac7ce63-e768-454d-96f3-3a00e8e1df69")
    parser.add_argument("--project-id", default="content_campaign_20251215_134931_c9b794db")
    parser.add_argument("--lens-id", default="9f9f6262-8fc4-421e-8835-66474af69eb9")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--command-id", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--reference-ids", default=",".join(DEFAULT_REFS))
    parser.add_argument("--target-duration-sec", type=int, default=90)
    parser.add_argument("--duration-tolerance-sec", type=float, default=4.0)
    parser.add_argument("--scene-count-target", type=int, default=45)
    parser.add_argument("--scene-count-floor", type=int, default=40)
    parser.add_argument("--max-rounds", type=int, default=1)
    parser.add_argument("--http-timeout-seconds", type=int, default=120)
    parser.add_argument("--command-timeout-seconds", type=int, default=1200)
    parser.add_argument("--post-command-poll-seconds", type=int, default=900)
    parser.add_argument("--post-command-poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--skip-quota-preflight", action="store_true")
    parser.add_argument("--codex-quota-max-runtime-probes", type=int, default=4)
    parser.add_argument("--codex-quota-target-successes", type=int, default=2)
    parser.add_argument("--codex-quota-timeout-seconds", type=int, default=90)
    parser.add_argument("--codex-quota-stall-timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--required-codex-login-email",
        default=os.environ.get("PD_E2E_REQUIRED_CODEX_LOGIN_EMAIL", ""),
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        result = run(parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("status") == "passed" else 2)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise
