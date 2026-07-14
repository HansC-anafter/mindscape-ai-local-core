from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .api_client import api_post


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def load_reference_visual_evidence(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    values = payload if isinstance(payload, list) else _record(payload).get("visual_evidence")
    if not isinstance(values, list):
        raise ValueError("practice_diary_reference_visual_evidence_missing")
    assets = [
        dict(item)
        for item in values
        if isinstance(item, Mapping)
        and item.get("role") == "reference"
        and item.get("source_kind") == "reference_asset"
    ]
    if not assets:
        raise ValueError("practice_diary_reference_visual_evidence_empty")
    if len({str(item.get("asset_id") or "") for item in assets}) != len(assets):
        raise ValueError("practice_diary_reference_visual_evidence_duplicate_asset_id")
    return assets


def materialize_practice_diary(
    args: Any,
    *,
    live_session_id: str,
    live_practice_rollup: Mapping[str, Any],
    practice_review_projection: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    visual_path = str(
        getattr(args, "practice_diary_reference_visual_evidence_path", "") or ""
    ).strip()
    reference_visuals = (
        load_reference_visual_evidence(visual_path) if visual_path else []
    )
    rollup = dict(live_practice_rollup)
    metadata = _record(rollup.get("metadata"))
    practice_session_id = str(rollup.get("practice_session_id") or "").strip()
    source_report_ref = str(metadata.get("source_motion_rollup_ref") or "").strip()
    request = {
        "workspace_id": args.workspace_id,
        "meeting_session_id": args.meeting_id,
        "live_session_id": live_session_id,
        "title": f"Live YogaCoach practice · {practice_session_id}",
        "user_goal": args.user_goal or None,
        "source_report_ref": source_report_ref or None,
        "live_practice_rollup": rollup,
        "practice_review_projection": dict(practice_review_projection),
        "visual_evidence": reference_visuals,
    }
    response = api_post(
        args.api_base,
        "/api/v1/capabilities/yogacoach/practice-diaries/materialize",
        request,
        timeout_sec=args.api_timeout_sec,
        retry_count=args.api_retry_count,
        retry_backoff_sec=args.api_retry_backoff_sec,
    )
    summary = _record(response.get("summary"))
    if not str(summary.get("diary_id") or "").strip():
        raise RuntimeError("practice_diary_materialize_returned_no_diary_id")
    return request, response


__all__ = ["load_reference_visual_evidence", "materialize_practice_diary"]
