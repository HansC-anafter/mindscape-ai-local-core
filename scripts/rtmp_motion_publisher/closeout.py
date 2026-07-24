from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .events import emit
from .practice_diary import materialize_practice_diary
from .source_uri import public_input_uri


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_backend_app_path() -> None:
    backend_app = _repo_root() / "backend" / "app"
    if str(backend_app) not in sys.path:
        sys.path.insert(0, str(backend_app))


def _safe_stem(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "-"
        for character in value.strip()
    ).strip("-")
    return cleaned or "yogacoach-closeout"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _input_asset_kind(value: str) -> str:
    source = str(value or "").strip()
    if not source:
        return "unknown"
    if source.startswith("rtmp://") or source.startswith("rtmps://"):
        return "rtmp_capture"
    if source.startswith("rtsp://") or source.startswith("rtsps://"):
        return "relay_capture"
    if source.startswith("avfoundation:"):
        return "avfoundation_capture"
    path = Path(source)
    try:
        if path.exists():
            return (
                "bilibili_m4s_file"
                if "bilibili" in path.name.lower()
                else "file_replay"
            )
    except OSError:
        return "stream_replay"
    return "stream_replay"


def _source_mode(input_asset_kind: str) -> str:
    return (
        "live_capture"
        if input_asset_kind in {
            "rtmp_capture",
            "relay_capture",
            "avfoundation_capture",
        }
        else "reference_replay"
    )


def _receiver_metric_families(motion_rollup: dict[str, Any]) -> list[str]:
    families = []
    digests = motion_rollup.get("motion_window_digests")
    if not isinstance(digests, list):
        return families
    for family in ("dwpose_node_deltas", "sway_metrics", "phase_metrics"):
        if any(isinstance(digest, dict) and digest.get(family) for digest in digests):
            families.append(family)
    return families


def emit_yogacoach_closeout(
    args: argparse.Namespace,
    *,
    live_session_id: str,
    rollup_response: dict[str, Any] | None,
    learner_visual_evidence: dict[str, Any] | None = None,
    reference_visual_evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not args.emit_yogacoach_summary:
        return None
    if not isinstance(rollup_response, dict):
        emit({"event": "yogacoach_closeout_skipped", "reason": "missing_rollup_response"})
        return None
    motion_rollup = rollup_response.get("summary")
    if not isinstance(motion_rollup, dict):
        emit({"event": "yogacoach_closeout_skipped", "reason": "missing_rollup_summary"})
        return None

    _ensure_backend_app_path()
    from capabilities.yogacoach.services.motion_runtime_rollup_adapter import (
        build_live_practice_rollup_from_motion_session_rollup,
    )
    from capabilities.yogacoach.tools.yogacoach_build_practice_feedback_report import (
        build_practice_feedback_report,
    )
    from capabilities.yogacoach.tools.yogacoach_build_student_practice_summary import (
        build_student_practice_summary,
    )

    practice_session_id = args.practice_session_id or f"{args.source_session_id}:live_guidance"
    input_asset_kind = _input_asset_kind(args.rtmp_url)
    source_mode = _source_mode(input_asset_kind)
    input_evidence = {
        "input_asset_kind": input_asset_kind,
        "input_uri": public_input_uri(args.rtmp_url),
        "reference_url": args.yogacoach_reference_url or None,
        "source_session_id": args.source_session_id,
        "receiver_motion_window_count": int(motion_rollup.get("window_count") or 0),
        "receiver_metric_families": _receiver_metric_families(motion_rollup),
    }
    closeout_metadata: dict[str, Any] = {
        "source_surface": "live_motion_receiver_closeout",
        "source_live_session_id": live_session_id,
        "publisher_expected_duration_ms": args.expected_duration_ms or None,
        "e2e_source_mode": source_mode,
        "learner_visual_evidence": learner_visual_evidence
        or {"status": "unavailable", "reason": "not_captured", "assets": []},
        "reference_visual_evidence": reference_visual_evidence
        or {"status": "unavailable", "reason": "not_captured", "assets": []},
    }
    motion_rollup_metadata = motion_rollup.get("metadata")
    stream_cost = (
        motion_rollup_metadata.get("stream_cost")
        if isinstance(motion_rollup_metadata, dict)
        else None
    )
    if isinstance(stream_cost, dict):
        closeout_metadata["stream_cost"] = stream_cost
    if source_mode == "live_capture":
        closeout_metadata["learner_capture_input_evidence"] = input_evidence
    else:
        closeout_metadata["reference_replay_evidence"] = input_evidence
    live_rollup = build_live_practice_rollup_from_motion_session_rollup(
        motion_rollup,
        practice_session_id=practice_session_id,
        teacher_library_ref=args.yogacoach_reference_url or None,
        reference_url=args.yogacoach_reference_url or None,
        metadata=closeout_metadata,
    )
    summary = build_student_practice_summary(
        live_rollup,
        user_id=args.user_id,
        user_goal=args.user_goal or None,
    )
    report = build_practice_feedback_report(
        practice_review_projection=summary.get("practice_review_projection"),
        live_practice_rollup=live_rollup,
        report_title="YogaCoach live practice feedback",
        suggested_file_name=f"yogacoach-live-practice-{_safe_stem(live_session_id)}.html",
    )
    projection = summary.get("practice_review_projection") or {}
    course_match_score = (
        projection.get("course_match_score") if isinstance(projection, dict) else {}
    )
    diary_request: dict[str, Any] | None = None
    diary_response: dict[str, Any] | None = None
    if getattr(args, "materialize_practice_diary", False):
        diary_request, diary_response = materialize_practice_diary(
            args,
            live_session_id=live_session_id,
            live_practice_rollup=live_rollup.model_dump(mode="json"),
            practice_review_projection=projection,
        )
        diary_summary = diary_response.get("summary") or {}
        emit(
            {
                "event": "practice_diary_materialized",
                "diary_id": diary_summary.get("diary_id"),
                "revision": diary_summary.get("revision"),
                "chapter_count": diary_summary.get("chapter_count"),
                "validation_passed": diary_summary.get("validation_passed"),
            }
        )
    output_paths: dict[str, str] = {}
    if args.yogacoach_summary_output_dir:
        output_dir = Path(args.yogacoach_summary_output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = _safe_stem(live_session_id)
        live_rollup_path = output_dir / f"{stem}.live-practice-rollup.json"
        summary_path = output_dir / f"{stem}.student-practice-summary.json"
        projection_path = output_dir / f"{stem}.practice-review-projection.json"
        report_path = output_dir / f"{stem}.practice-feedback-report.json"
        html_path = output_dir / f"{stem}.practice-feedback-report.html"
        diary_request_path = output_dir / f"{stem}.practice-diary-request.json"
        diary_response_path = output_dir / f"{stem}.practice-diary-response.json"
        _write_json(live_rollup_path, live_rollup.model_dump(mode="json"))
        _write_json(summary_path, summary)
        _write_json(projection_path, projection)
        _write_json(report_path, {key: value for key, value in report.items() if key != "html"})
        html_path.write_text(str(report.get("html") or ""), encoding="utf-8")
        if diary_request is not None and diary_response is not None:
            _write_json(diary_request_path, diary_request)
            _write_json(diary_response_path, diary_response)
        output_paths = {
            "live_practice_rollup": str(live_rollup_path),
            "student_practice_summary": str(summary_path),
            "practice_review_projection": str(projection_path),
            "practice_feedback_report": str(report_path),
            "practice_feedback_html": str(html_path),
        }
        if diary_request is not None and diary_response is not None:
            output_paths.update(
                {
                    "practice_diary_request": str(diary_request_path),
                    "practice_diary_response": str(diary_response_path),
                }
            )

    result = {
        "practice_session_id": live_rollup.practice_session_id,
        "live_session_id": live_session_id,
        "window_count": live_rollup.window_count,
        "summary_confidence": live_rollup.summary_confidence,
        "projection_status": projection.get("projection_status")
        if isinstance(projection, dict)
        else None,
        "course_chapter_count": len(projection.get("course_chapters") or [])
        if isinstance(projection, dict)
        else 0,
        "learner_segment_count": len(projection.get("learner_practice_segments") or [])
        if isinstance(projection, dict)
        else 0,
        "course_match_verdict": course_match_score.get("overall_verdict")
        if isinstance(course_match_score, dict)
        else None,
        "course_match_confidence": course_match_score.get("confidence")
        if isinstance(course_match_score, dict)
        else None,
        "e2e_acceptance": report.get("e2e_acceptance"),
        "learner_visual_evidence_status": (
            learner_visual_evidence or {}
        ).get("status"),
        "learner_visual_evidence_asset_count": len(
            (learner_visual_evidence or {}).get("assets") or []
        ),
        "reference_visual_evidence_status": (
            reference_visual_evidence or {}
        ).get("status"),
        "reference_visual_evidence_asset_count": len(
            (reference_visual_evidence or {}).get("assets") or []
        ),
        "practice_diary": (
            (diary_response or {}).get("summary")
            if diary_response is not None
            else None
        ),
        "output_paths": output_paths,
    }
    emit({"event": "yogacoach_closeout_finished", **result})
    return result


__all__ = ["emit_yogacoach_closeout"]
