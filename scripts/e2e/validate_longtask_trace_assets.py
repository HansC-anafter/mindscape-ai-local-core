#!/usr/bin/env python3
"""Validate long-task E2E trace assets against a fixed theme spec."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _sync_summary_acceptance_status(trace_dir: Path, acceptance_status: str) -> None:
    summary_path = trace_dir / "summary.json"
    if not summary_path.exists():
        return
    try:
        payload = _load_json(summary_path)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("acceptance_status") == acceptance_status:
        return
    payload["acceptance_status"] = acceptance_status
    _write_json(summary_path, payload)


def _slugify(filename: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", Path(filename).stem.lower()).strip("_")


def _artifact_inventory_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("artifacts"), list):
        return [item for item in payload["artifacts"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _coerce_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _parse_timestamp(value: Any) -> Optional[datetime]:
    text = _coerce_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _infer_workspace_root(trace_dir: Path) -> Optional[Path]:
    candidates = []
    if len(trace_dir.parents) >= 4:
        candidates.append(trace_dir.parents[3])
    candidates.append(Path.cwd())
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "data" / "e2e-traces").exists():
            return candidate
    return candidates[0] if candidates else None


def _workspace_file_is_current_run(path: Path, session_payload: Dict[str, Any]) -> bool:
    if not path.is_file():
        return False

    session_start = _parse_timestamp(session_payload.get("started_at"))
    compile_job = session_payload.get("compile_job") or {}
    session_end = (
        _parse_timestamp(session_payload.get("ended_at"))
        or _parse_timestamp(compile_job.get("completed_at"))
        or _parse_timestamp(compile_job.get("updated_at"))
    )
    file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    if session_start and file_mtime < session_start - timedelta(seconds=5):
        return False
    if session_end and file_mtime > session_end + timedelta(minutes=5):
        return False
    return True


def _looks_like_runtime_quota_or_rate_limit(text: Optional[str]) -> bool:
    normalized = _coerce_text(text)
    if not normalized:
        return False
    lower = normalized.lower()
    patterns = (
        "usage limit",
        "rate limit",
        "rate-limit",
        "quota exceeded",
        "quota exhausted",
        "insufficient_quota",
        "resource_exhausted",
        "try again in",
    )
    return any(pattern in lower for pattern in patterns)


def _detect_runtime_quota_block(session_payload: Dict[str, Any]) -> bool:
    metadata = session_payload.get("metadata") or {}
    compile_job = session_payload.get("compile_job") or {}
    candidates = [
        metadata.get("pipeline_stage_error"),
        metadata.get("last_round_failure"),
        metadata.get("last_round_status"),
        compile_job.get("error"),
    ]
    if any(_looks_like_runtime_quota_or_rate_limit(candidate) for candidate in candidates):
        return True

    if _coerce_text(metadata.get("last_round_status")) == "quota_fallback":
        return True

    compile_job_metadata = compile_job.get("metadata") or {}
    if _coerce_text(compile_job_metadata.get("dispatch_status")) == "quota_blocked":
        return True

    for item in session_payload.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        if any(
            _looks_like_runtime_quota_or_rate_limit(item.get(key))
            for key in ("error", "landing_error")
        ):
            return True

    for trace in session_payload.get("traces") or []:
        if not isinstance(trace, dict):
            continue
        if _coerce_text(trace.get("reason")) == "runtime_quota_or_rate_limit":
            return True
        if any(
            _looks_like_runtime_quota_or_rate_limit(trace.get(key))
            for key in ("error", "message", "detail")
        ):
            return True

    return False


def _collect_session_execution_ids(session_payload: Dict[str, Any]) -> set[str]:
    execution_ids: set[str] = set()
    for item in session_payload.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("task_id"),
            item.get("execution_id"),
        ):
            normalized = _coerce_text(candidate)
            if normalized:
                execution_ids.add(normalized)
        for key in ("task_ids", "execution_ids"):
            values = item.get(key) or []
            if not isinstance(values, list):
                continue
            for candidate in values:
                normalized = _coerce_text(candidate)
                if normalized:
                    execution_ids.add(normalized)
    return execution_ids


def _filter_artifacts_for_session(
    artifacts: List[Dict[str, Any]],
    session_payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    project_id = _coerce_text(session_payload.get("project_id"))
    thread_id = _coerce_text(session_payload.get("thread_id"))
    meeting_session_id = _coerce_text(session_payload.get("id"))
    session_execution_ids = _collect_session_execution_ids(session_payload)

    if not any((project_id, thread_id, meeting_session_id, session_execution_ids)):
        return list(artifacts)

    scoped: List[Dict[str, Any]] = []
    for artifact in artifacts:
        metadata = artifact.get("metadata") or {}
        provenance = metadata.get("provenance") or {}

        candidate_execution_ids = {
            normalized
            for normalized in (
                _coerce_text(artifact.get("execution_id")),
                _coerce_text(metadata.get("execution_id")),
                _coerce_text(metadata.get("navigate_to")),
                _coerce_text(provenance.get("source_task_id")),
            )
            if normalized
        }
        if session_execution_ids and candidate_execution_ids.intersection(
            session_execution_ids
        ):
            scoped.append(artifact)
            continue

        artifact_project_id = (
            _coerce_text(metadata.get("project_id"))
            or _coerce_text(provenance.get("project_id"))
            or _coerce_text(artifact.get("project_id"))
        )
        if project_id and artifact_project_id == project_id:
            scoped.append(artifact)
            continue

        artifact_thread_id = _coerce_text(artifact.get("thread_id")) or _coerce_text(
            metadata.get("thread_id")
        )
        if thread_id and artifact_thread_id == thread_id:
            scoped.append(artifact)
            continue

        artifact_meeting_session_id = _coerce_text(
            provenance.get("meeting_session_id")
        ) or _coerce_text(metadata.get("meeting_session_id"))
        if meeting_session_id and artifact_meeting_session_id == meeting_session_id:
            scoped.append(artifact)

    return scoped


def _artifact_match_score(artifact: Dict[str, Any], filename: str) -> Tuple[int, Optional[str]]:
    metadata = artifact.get("metadata") or {}
    title = _coerce_text(artifact.get("title"))
    if title == filename:
        return 50, "title"

    deliverable_path = _coerce_text(metadata.get("deliverable_path"))
    if deliverable_path and Path(deliverable_path).name == filename:
        return 40, "metadata.deliverable_path"

    attachment_filenames = metadata.get("attachment_filenames") or []
    if isinstance(attachment_filenames, list) and filename in attachment_filenames:
        return 35, "metadata.attachment_filenames"

    landing = metadata.get("landing") or {}
    landing_attachments = landing.get("attachments") or []
    if isinstance(landing_attachments, list):
        for raw_path in landing_attachments:
            if isinstance(raw_path, str) and Path(raw_path).name == filename:
                return 30, "metadata.landing.attachments"

    file_path = _coerce_text(artifact.get("file_path"))
    if file_path and Path(file_path).name == filename:
        return 25, "file_path"

    return 0, None


def _resolve_deliverable_artifact(
    artifacts: List[Dict[str, Any]], filename: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    best_artifact: Optional[Dict[str, Any]] = None
    best_source: Optional[str] = None
    best_score = 0
    for artifact in artifacts:
        score, source = _artifact_match_score(artifact, filename)
        if score > best_score:
            best_score = score
            best_artifact = artifact
            best_source = source
    return best_artifact, best_source, best_score


def _candidate_content_paths(
    artifact: Optional[Dict[str, Any]],
    filename: str,
    *,
    workspace_root: Optional[Path],
    session_payload: Dict[str, Any],
) -> List[Tuple[Path, str]]:
    candidates: List[Tuple[Path, str]] = []
    if workspace_root:
        workspace_file = workspace_root / filename
        if _workspace_file_is_current_run(workspace_file, session_payload):
            candidates.append((workspace_file, "workspace_root.current_run"))

    if artifact is None:
        return candidates

    metadata = artifact.get("metadata") or {}
    landing = metadata.get("landing") or {}

    file_path = _coerce_text(artifact.get("file_path"))
    if file_path:
        path = Path(file_path)
        candidates.append((path, "artifact.file_path"))
        candidates.append((path / "attachments" / filename, "artifact.file_path.attachments"))

    artifact_dir = _coerce_text(landing.get("artifact_dir"))
    if artifact_dir:
        path = Path(artifact_dir)
        candidates.append((path / "attachments" / filename, "landing.artifact_dir.attachments"))

    landing_attachments = landing.get("attachments") or []
    if isinstance(landing_attachments, list):
        for raw_path in landing_attachments:
            if isinstance(raw_path, str) and Path(raw_path).name == filename:
                candidates.append((Path(raw_path), "landing.attachments"))

    actual_file_path = _coerce_text(metadata.get("actual_file_path"))
    if actual_file_path:
        candidates.append((Path(actual_file_path), "metadata.actual_file_path"))

    legacy_file_path = _coerce_text(metadata.get("file_path"))
    if legacy_file_path:
        path = Path(legacy_file_path)
        candidates.append((path, "metadata.file_path"))
        candidates.append((path / filename, "metadata.file_path.relative"))

    deduped: List[Tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in candidates:
        key = str(path)
        if key not in seen:
            deduped.append((path, source))
            seen.add(key)
    return deduped


def _read_deliverable_content(
    artifact: Optional[Dict[str, Any]],
    filename: str,
    *,
    workspace_root: Optional[Path],
    session_payload: Dict[str, Any],
) -> Dict[str, Any]:
    for path, source in _candidate_content_paths(
        artifact,
        filename,
        workspace_root=workspace_root,
        session_payload=session_payload,
    ):
        if path.is_file():
            try:
                return {
                    "content_found": True,
                    "content_source": source,
                    "content_path": str(path),
                    "content": path.read_text(encoding="utf-8"),
                }
            except UnicodeDecodeError:
                return {
                    "content_found": False,
                    "content_source": source,
                    "content_path": str(path),
                    "content": None,
                    "error": "non_utf8_attachment",
                }

    if artifact is None:
        return {
            "content_found": False,
            "content_source": None,
            "content_path": None,
            "content": None,
        }

    is_markdown_deliverable = filename.lower().endswith(".md")

    content_payload = artifact.get("content")
    if isinstance(content_payload, dict):
        output = _coerce_text(content_payload.get("output"))
        if output:
            if is_markdown_deliverable:
                return {
                    "content_found": False,
                    "content_source": "artifact.content.output",
                    "content_path": None,
                    "content": output,
                    "placeholder_summary_fallback": True,
                }
            return {
                "content_found": True,
                "content_source": "artifact.content.output",
                "content_path": None,
                "content": output,
            }

    description = _coerce_text(artifact.get("description"))
    if description:
        if is_markdown_deliverable:
            return {
                "content_found": False,
                "content_source": "artifact.description",
                "content_path": None,
                "content": description,
                "placeholder_summary_fallback": True,
            }
        return {
            "content_found": True,
            "content_source": "artifact.description",
            "content_path": None,
            "content": description,
        }

    return {
        "content_found": False,
        "content_source": None,
        "content_path": None,
        "content": None,
    }


def _line_based_placeholder_hits(text: str, patterns: Iterable[str]) -> List[str]:
    hits: List[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.MULTILINE):
            hits.append(pattern)
    return hits


def _count_day_entries(text: str) -> int:
    pattern = re.compile(r"(?im)^\s{0,3}(?:[#>*\-\d\.\s]*)?(day\s*[1-7]|第\s*[1-7]\s*天)\b")
    return len(pattern.findall(text))


def _count_hook_entries(text: str) -> int:
    marker_hits = len(re.findall(r"(?m)^\s{0,3}(?:[-*]|\d+\.)\s+", text))
    context_hits = len(re.findall(r"適用情境", text))
    return max(marker_hits, context_hits)


def _extract_blocking_items(session_payload: Dict[str, Any], filename: str) -> List[Dict[str, Any]]:
    blocked: List[Dict[str, Any]] = []
    stem = Path(filename).stem.replace("_", " ").lower()
    for item in session_payload.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        status = _coerce_text(item.get("status")) or ""
        if status not in {"policy_blocked", "dependency_blocked"}:
            continue
        haystack = json.dumps(item, ensure_ascii=False).lower()
        if filename.lower() in haystack or stem in haystack:
            blocked.append(item)
    return blocked


def _evaluate_deliverable(
    spec_item: Dict[str, Any],
    artifacts: List[Dict[str, Any]],
    session_payload: Dict[str, Any],
    quality_rules: Dict[str, Any],
    *,
    workspace_root: Optional[Path],
) -> Dict[str, Any]:
    filename = spec_item["filename"]
    artifact, matched_by, match_score = _resolve_deliverable_artifact(artifacts, filename)
    content_snapshot = _read_deliverable_content(
        artifact,
        filename,
        workspace_root=workspace_root,
        session_payload=session_payload,
    )
    content = content_snapshot.get("content") or ""
    workspace_file_landed = content_snapshot.get("content_source") == "workspace_root.current_run"
    if artifact is None and workspace_file_landed:
        matched_by = "workspace_root.current_run"
        match_score = 100
    named_asset_required = filename.lower().endswith(".md")
    named_asset_found = bool(content_snapshot.get("content_found")) and bool(
        content_snapshot.get("content_path")
    )
    placeholder_summary_fallback = bool(
        content_snapshot.get("placeholder_summary_fallback")
    )

    required_sections = spec_item.get("required_sections") or []
    missing_sections = [section for section in required_sections if section not in content]

    placeholder_tokens = [
        token for token in quality_rules.get("placeholder_tokens") or [] if token and token in content
    ]
    placeholder_patterns = quality_rules.get("line_placeholder_patterns") or []
    placeholder_pattern_hits = _line_based_placeholder_hits(content, placeholder_patterns)

    min_chars = int(spec_item.get("min_chars") or 0)
    chars_ok = len(content) >= min_chars if min_chars else bool(content)

    extra_checks: Dict[str, Any] = {}
    if spec_item.get("min_day_entries"):
        day_entries = _count_day_entries(content)
        extra_checks["day_entries_found"] = day_entries
        extra_checks["day_entries_required"] = int(spec_item["min_day_entries"])
        extra_checks["day_entries_ok"] = day_entries >= int(spec_item["min_day_entries"])
    if spec_item.get("min_hook_entries"):
        hook_entries = _count_hook_entries(content)
        extra_checks["hook_entries_found"] = hook_entries
        extra_checks["hook_entries_required"] = int(spec_item["min_hook_entries"])
        extra_checks["hook_entries_ok"] = hook_entries >= int(spec_item["min_hook_entries"])

    blocked_items = _extract_blocking_items(session_payload, filename)

    automated_pass = (
        (artifact is not None or workspace_file_landed)
        and bool(content_snapshot.get("content_found"))
        and (not named_asset_required or named_asset_found)
        and not missing_sections
        and chars_ok
        and not placeholder_tokens
        and not placeholder_pattern_hits
        and not placeholder_summary_fallback
        and not blocked_items
        and all(
            value is True
            for key, value in extra_checks.items()
            if key.endswith("_ok")
        )
    )

    result = {
        "filename": filename,
        "artifact_found": artifact is not None or workspace_file_landed,
        "artifact_id": artifact.get("id") if artifact else None,
        "artifact_title": artifact.get("title") if artifact else None,
        "matched_by": matched_by,
        "match_score": match_score,
        "named_asset_required": named_asset_required,
        "named_asset_found": named_asset_found,
        "content_found": content_snapshot.get("content_found", False),
        "content_source": content_snapshot.get("content_source"),
        "content_path": content_snapshot.get("content_path"),
        "content_chars": len(content),
        "required_sections": required_sections,
        "missing_sections": missing_sections,
        "placeholder_summary_fallback": placeholder_summary_fallback,
        "placeholder_tokens_found": placeholder_tokens,
        "placeholder_pattern_hits": placeholder_pattern_hits,
        "blocked_items": blocked_items,
        "automated_pass": automated_pass,
        "review_required": True,
        "extra_checks": extra_checks,
    }
    result["content"] = content
    return result


def _evaluate_cross_doc_rules(
    deliverable_results: List[Dict[str, Any]], cross_doc_rules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    by_name = {item["filename"]: item for item in deliverable_results}
    persona = by_name.get("persona_operating_system.md")
    calendar = by_name.get("instagram_week1_calendar.md")
    hooks = by_name.get("reel_hook_bank.md")

    results: List[Dict[str, Any]] = []
    for rule in cross_doc_rules:
        rule_id = rule["id"]
        status = "review_required"
        if rule_id == "persona_calendar_cta_alignment":
            if persona and calendar and persona["automated_pass"] and calendar["automated_pass"]:
                status = "review_required"
            else:
                status = "blocked"
        elif rule_id == "persona_hook_promise_alignment":
            if persona and hooks and persona["automated_pass"] and hooks["automated_pass"]:
                status = "review_required"
            else:
                status = "blocked"
        elif rule_id == "calendar_hook_alignment":
            if calendar and hooks and calendar["automated_pass"] and hooks["automated_pass"]:
                status = "review_required"
            else:
                status = "blocked"
        results.append(
            {
                "id": rule_id,
                "description": rule.get("description"),
                "status": status,
            }
        )
    return results


def _evaluate_governance(
    memory_detail: Optional[Dict[str, Any]], required_evidence: Dict[str, int]
) -> Dict[str, Any]:
    if not memory_detail:
        return {
            "pass": False,
            "reason": "memory_detail_missing",
            "evidence_counts": {},
            "missing_evidence": dict(required_evidence),
        }

    evidence = memory_detail.get("evidence") or []
    evidence_counts = Counter()
    for item in evidence:
        if isinstance(item, dict):
            evidence_type = _coerce_text(item.get("evidence_type"))
            if evidence_type:
                evidence_counts[evidence_type] += 1

    missing = {
        evidence_type: required_count
        for evidence_type, required_count in required_evidence.items()
        if evidence_counts.get(evidence_type, 0) < required_count
    }
    return {
        "pass": not missing,
        "reason": None if not missing else "insufficient_evidence",
        "evidence_counts": dict(evidence_counts),
        "missing_evidence": missing,
        "memory_item": memory_detail.get("memory_item"),
        "evidence_coverage": memory_detail.get("evidence_coverage"),
    }


def _build_markdown_scorecard(
    scorecard: Dict[str, Any],
    verdict: Dict[str, Any],
) -> str:
    lines = [
        "# Long-task Quality Scorecard",
        "",
        f"- review_mode: `{scorecard['review_mode']}`",
        f"- final_status: `{verdict['status']}`",
        "",
        "## Deliverables",
        "",
        "| filename | asset | content | missing_sections | placeholders | automated | review |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for item in scorecard["deliverables"]:
        lines.append(
            "| {filename} | {asset} | {content} | {missing} | {placeholders} | {automated} | {review} |".format(
                filename=item["filename"],
                asset="pass" if item["artifact_found"] else "fail",
                content="pass" if item["content_found"] else "fail",
                missing=len(item["missing_sections"]),
                placeholders=len(item["placeholder_tokens_found"]) + len(item["placeholder_pattern_hits"]),
                automated="pass" if item["automated_pass"] else "fail",
                review="pending" if item["review_required"] else "n/a",
            )
        )

    lines.extend(
        [
            "",
            "## Cross-doc",
            "",
            "| rule | status |",
            "|---|---|",
        ]
    )
    for item in scorecard["cross_doc_rules"]:
        lines.append(f"| {item['id']} | {item['status']} |")

    lines.extend(
        [
            "",
            "## Governance",
            "",
            f"- pass: `{scorecard['governance']['pass']}`",
            f"- missing_evidence: `{scorecard['governance']['missing_evidence']}`",
            "",
            "## Blocking Issues",
            "",
        ]
    )
    if verdict["blocking_issues"]:
        lines.extend([f"- {issue}" for issue in verdict["blocking_issues"]])
    else:
        lines.append("- none")
    return "\n".join(lines)


def validate_trace(
    *,
    trace_dir: Path,
    spec_path: Path,
    review_mode: str,
    review_result_file: Optional[Path],
) -> int:
    spec = _load_json(spec_path)
    session_payload = _load_json(trace_dir / "03_session_after_close.json")
    artifact_inventory = _load_json(trace_dir / "10_artifact_inventory.json")
    all_artifacts = _artifact_inventory_items(artifact_inventory)
    artifacts = _filter_artifacts_for_session(all_artifacts, session_payload)
    workspace_root = _infer_workspace_root(trace_dir)

    memory_detail_path = trace_dir / "15_governance_memory_detail.json"
    memory_detail = _load_json(memory_detail_path) if memory_detail_path.exists() else None

    deliverable_results = [
        _evaluate_deliverable(
            spec_item=deliverable,
            artifacts=artifacts,
            session_payload=session_payload,
            quality_rules=spec.get("quality_rules") or {},
            workspace_root=workspace_root,
        )
        for deliverable in spec.get("deliverables") or []
    ]

    for item in deliverable_results:
        slug = _slugify(item["filename"])
        output_path = trace_dir / f"{11 + list(spec.get('deliverables') or []).index(next(d for d in spec['deliverables'] if d['filename'] == item['filename'])):02d}_deliverable_{slug}.json"
        snapshot = {
            "filename": item["filename"],
            "artifact_id": item["artifact_id"],
            "artifact_title": item["artifact_title"],
            "matched_by": item["matched_by"],
            "content_found": item["content_found"],
            "content_source": item["content_source"],
            "content_path": item["content_path"],
            "content_chars": item["content_chars"],
            "content": item["content"],
        }
        _write_json(output_path, snapshot)

    cross_doc_results = _evaluate_cross_doc_rules(
        deliverable_results,
        spec.get("cross_doc_rules") or [],
    )
    governance = _evaluate_governance(
        memory_detail,
        spec.get("required_governance_evidence") or {},
    )

    orchestration_pass = (
        (_coerce_text(session_payload.get("status")) == "closed")
        and (_coerce_text((session_payload.get("metadata") or {}).get("pipeline_stage")) == "finalize")
        and (_coerce_text((session_payload.get("metadata") or {}).get("pipeline_stage_status")) == "completed")
    )
    asset_pass = all(item["artifact_found"] and item["content_found"] for item in deliverable_results) and all(
        not item["blocked_items"] for item in deliverable_results
    )
    automated_quality_pass = all(item["automated_pass"] for item in deliverable_results)

    review_result = None
    if review_result_file and review_result_file.exists():
        review_result = _load_json(review_result_file)
    review_status = "pending_review"
    if review_result:
        review_status = "pass" if review_result.get("approved") else "fail"
    elif review_mode == "explicit_runtime":
        review_status = "pending_review"

    scorecard = {
        "theme_id": spec.get("theme_id"),
        "review_mode": review_mode,
        "artifact_scope": {
            "workspace_artifact_count": len(all_artifacts),
            "session_scoped_artifact_count": len(artifacts),
            "project_id": _coerce_text(session_payload.get("project_id")),
            "thread_id": _coerce_text(session_payload.get("thread_id")),
        },
        "deliverables": [
            {key: value for key, value in item.items() if key != "content"}
            for item in deliverable_results
        ],
        "cross_doc_rules": cross_doc_results,
        "governance": governance,
        "levels": {
            "l1_orchestration_pass": orchestration_pass,
            "l2_asset_landing_pass": asset_pass,
            "l3_automated_quality_pass": automated_quality_pass,
            "l3_review_status": review_status,
            "l4_governance_pass": governance["pass"],
        },
    }

    runtime_quota_blocked = _detect_runtime_quota_block(session_payload)

    blocking_issues: List[str] = []
    if not orchestration_pass:
        if runtime_quota_blocked:
            blocking_issues.append(
                "Runtime quota or rate-limit blocked orchestration before finalize completed."
            )
        else:
            blocking_issues.append("Session did not reach closed + finalize completed.")
    if not asset_pass:
        if runtime_quota_blocked:
            blocking_issues.append(
                "Runtime quota or rate-limit blocked one or more deliverables before named assets landed."
            )
        else:
            blocking_issues.append("One or more deliverables did not land as readable named assets.")
    if not automated_quality_pass:
        blocking_issues.append("One or more deliverables failed automated quality checks.")
    if not governance["pass"]:
        blocking_issues.append("Canonical memory evidence coverage is insufficient.")
    if review_status == "pending_review":
        blocking_issues.append("Human or explicit runtime review is still required for L3.")
    elif review_status == "fail":
        blocking_issues.append("Reviewer rejected the deliverables.")

    if runtime_quota_blocked and not orchestration_pass:
        final_status = "l1_runtime_quota_blocked"
    elif runtime_quota_blocked and not asset_pass:
        final_status = "l2_runtime_quota_blocked"
    elif not orchestration_pass:
        final_status = "l1_orchestration_fail"
    elif not asset_pass:
        final_status = "l2_asset_fail"
    elif not automated_quality_pass or review_status == "fail":
        final_status = "l3_quality_fail"
    elif not governance["pass"]:
        final_status = "l4_governance_fail"
    elif review_status == "pending_review":
        final_status = "l3_review_required"
    else:
        final_status = "full_pass"

    verdict = {
        "status": final_status,
        "theme_id": spec.get("theme_id"),
        "review_mode": review_mode,
        "levels": {
            "l1_orchestration": "pass" if orchestration_pass else "fail",
            "l2_asset_landing": "pass" if asset_pass else "fail",
            "l3_output_quality": (
                "pass" if automated_quality_pass and review_status == "pass"
                else "pending_review" if automated_quality_pass and review_status == "pending_review"
                else "fail"
            ),
            "l4_governance": "pass" if governance["pass"] else "fail",
        },
        "blocking_issues": blocking_issues,
        "runtime_quota_blocked": runtime_quota_blocked,
    }

    _write_json(trace_dir / "14_quality_scorecard.json", scorecard)
    _write_text(trace_dir / "14_quality_scorecard.md", _build_markdown_scorecard(scorecard, verdict))
    _write_json(trace_dir / "16_acceptance_verdict.json", verdict)
    _sync_summary_acceptance_status(trace_dir, final_status)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument(
        "--review-mode",
        choices=("explicit_runtime", "human_required"),
        default="human_required",
    )
    parser.add_argument("--review-result-file", type=Path, default=None)
    args = parser.parse_args(argv)

    trace_dir = args.trace_dir.resolve()
    spec_path = args.spec.resolve()

    required_files = [
        trace_dir / "03_session_after_close.json",
        trace_dir / "10_artifact_inventory.json",
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        print(json.dumps({"error": "missing_required_files", "files": missing}, ensure_ascii=False), file=sys.stderr)
        return 2

    return validate_trace(
        trace_dir=trace_dir,
        spec_path=spec_path,
        review_mode=args.review_mode,
        review_result_file=args.review_result_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
