"""Workflow evidence scope, ordering, and budget helpers."""

from typing import Any, Dict, List


def _workflow_evidence_requires_thread_scope(meeting: Any) -> bool:
    session = getattr(meeting, "session", None)
    meeting_type = str(getattr(session, "meeting_type", "") or "").lower()
    if meeting_type in {"e2e_validation", "command_validation"}:
        return True

    metadata = dict(getattr(session, "metadata", None) or {})
    request_contract = metadata.get("request_contract")
    if _value_has_selected_source_refs(request_contract):
        return True

    agenda_text = " ".join(
        str(item).lower() for item in list(getattr(session, "agenda", None) or [])
    )
    return (
        "selected" in agenda_text
        and "reference" in agenda_text
        and ("storyboard" in agenda_text or "reels" in agenda_text)
    )


def _value_has_selected_source_refs(value: Any) -> bool:
    if isinstance(value, dict):
        refs = value.get("selected_object_refs") or value.get("context_attachments")
        if isinstance(refs, list) and refs:
            return True
        return any(_value_has_selected_source_refs(item) for item in value.values())
    if isinstance(value, list):
        return any(_value_has_selected_source_refs(item) for item in value)
    return False


def _append_section(parts: List[str], title: str, lines: List[str]) -> None:
    clean_lines = [line for line in lines if line]
    if not clean_lines:
        return
    parts.append(f"{title}:")
    parts.extend(clean_lines[:3])


def _infer_workflow_evidence_profile(meeting: Any) -> str:
    meeting_type = str(getattr(getattr(meeting, "session", None), "meeting_type", "") or "").lower()
    agenda = getattr(getattr(meeting, "session", None), "agenda", None) or []
    agenda_text = " ".join(str(item).lower() for item in agenda)
    combined = f"{meeting_type} {agenda_text}"

    if any(token in combined for token in ("meta", "reflection", "retrospective", "retro")):
        return "reflection"
    if any(token in combined for token in ("review", "inspect", "audit", "evaluate", "feedback")):
        return "review"
    if any(token in combined for token in ("decision", "approve", "approval", "choose", "selection", "direction")):
        return "decision"
    return "general"


def _workflow_section_order(meeting_profile: str) -> List[str]:
    if meeting_profile == "review":
        return [
            "Recent stage checkpoints",
            "Recent governance outcomes",
            "Recent artifacts",
            "Recent execution outcomes",
            "Recent intent routing",
            "Latest lens continuity signal",
        ]
    if meeting_profile == "decision":
        return [
            "Recent governance outcomes",
            "Recent intent routing",
            "Recent execution outcomes",
            "Recent stage checkpoints",
            "Recent artifacts",
            "Latest lens continuity signal",
        ]
    if meeting_profile == "reflection":
        return [
            "Latest lens continuity signal",
            "Recent governance outcomes",
            "Recent intent routing",
            "Recent execution outcomes",
            "Recent stage checkpoints",
            "Recent artifacts",
        ]
    return [
        "Recent execution outcomes",
        "Recent stage checkpoints",
        "Recent governance outcomes",
        "Recent artifacts",
        "Recent intent routing",
        "Latest lens continuity signal",
    ]


def _workflow_section_budgets(meeting_profile: str) -> tuple[Dict[str, int], int]:
    if meeting_profile == "review":
        return (
            {
                "Recent stage checkpoints": 3,
                "Recent governance outcomes": 2,
                "Recent artifacts": 2,
                "Recent execution outcomes": 2,
                "Recent intent routing": 1,
                "Latest lens continuity signal": 1,
            },
            9,
        )
    if meeting_profile == "decision":
        return (
            {
                "Recent governance outcomes": 3,
                "Recent intent routing": 2,
                "Recent execution outcomes": 2,
                "Recent stage checkpoints": 1,
                "Recent artifacts": 1,
                "Latest lens continuity signal": 1,
            },
            8,
        )
    if meeting_profile == "reflection":
        return (
            {
                "Latest lens continuity signal": 1,
                "Recent governance outcomes": 2,
                "Recent intent routing": 2,
                "Recent execution outcomes": 2,
                "Recent stage checkpoints": 1,
                "Recent artifacts": 1,
            },
            8,
        )
    return (
        {
            "Recent execution outcomes": 3,
            "Recent stage checkpoints": 2,
            "Recent governance outcomes": 2,
            "Recent artifacts": 2,
            "Recent intent routing": 1,
            "Latest lens continuity signal": 1,
        },
        9,
    )


def _apply_workflow_evidence_budget(
    *,
    sections: Dict[str, List[str]],
    section_order: List[str],
    meeting_profile: str,
    selected_scope: str,
) -> tuple[Dict[str, List[str]], Dict[str, Any]]:
    section_limits, total_line_budget = _workflow_section_budgets(meeting_profile)
    bounded_sections: Dict[str, List[str]] = {}
    candidate_counts = {
        title: len([line for line in sections.get(title, []) if line])
        for title in section_order
    }
    selected_counts: Dict[str, int] = {}
    dropped_counts: Dict[str, int] = {}
    remaining_budget = total_line_budget

    for title in section_order:
        if remaining_budget <= 0:
            bounded_sections[title] = []
            selected_counts[title] = 0
            dropped_counts[title] = candidate_counts.get(title, 0)
            continue
        clean_lines = [line for line in sections.get(title, []) if line]
        section_budget = section_limits.get(title, 0)
        allowed = min(len(clean_lines), section_budget, remaining_budget)
        bounded_sections[title] = clean_lines[:allowed]
        selected_counts[title] = allowed
        dropped_counts[title] = max(len(clean_lines) - allowed, 0)
        remaining_budget -= allowed

    total_candidate_count = sum(candidate_counts.values())
    total_dropped_count = sum(dropped_counts.values())
    selected_line_count = sum(selected_counts.values())
    budget_utilization_ratio = (
        round(selected_line_count / total_line_budget, 3)
        if total_line_budget > 0
        else 0.0
    )

    diagnostics: Dict[str, Any] = {
        "profile": meeting_profile,
        "scope": selected_scope,
        "section_order": section_order,
        "section_limits": section_limits,
        "total_line_budget": total_line_budget,
        "total_candidate_count": total_candidate_count,
        "total_dropped_count": total_dropped_count,
        "candidate_counts": candidate_counts,
        "selected_counts": selected_counts,
        "dropped_counts": dropped_counts,
        "selected_line_count": selected_line_count,
        "budget_utilization_ratio": budget_utilization_ratio,
        "rendered": False,
    }
    return bounded_sections, diagnostics
