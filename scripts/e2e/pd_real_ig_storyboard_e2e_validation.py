"""Validation and artifact helpers for the PD real IG storyboard E2E."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from typing import Any

from pd_real_ig_storyboard_e2e_core import _as_dict, _as_list


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
