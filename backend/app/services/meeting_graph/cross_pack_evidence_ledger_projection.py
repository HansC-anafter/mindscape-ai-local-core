"""Cross-pack E2E evidence ledger projection for meeting execution graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)
from backend.app.services.meeting_graph.projection_utils import (
    _as_dict,
    _as_list,
    _edge,
    _json_output,
    _read_string,
    _safe_id,
    _short_id,
)


LEDGER_METADATA_KEY = "cross_pack_e2e_ledger"


@dataclass
class CrossPackEvidenceLedgerProjection:
    nodes: list[MeetingExecutionGraphNode] = field(default_factory=list)
    edges: list[MeetingExecutionGraphEdge] = field(default_factory=list)


def _status_for_case(status: str) -> str:
    normalized = status.lower().strip()
    if normalized in {"pass", "passed", "ready", "succeeded", "success"}:
        return "ready"
    if normalized in {"partial", "blocked", "degraded"}:
        return "blocked"
    if normalized in {"fail", "failed", "error"}:
        return "error"
    return "blocked"


def _case_title(case: Mapping[str, Any]) -> str:
    case_id = _read_string(case.get("case_id"), "E2E")
    title = _read_string(case.get("title"))
    return f"{case_id} {title}".strip()


def _case_detail(case: Mapping[str, Any]) -> str:
    packs = [
        _read_string(item)
        for item in _as_list(case.get("packs"))
        if _read_string(item)
    ]
    seed = _read_string(case.get("seed"))
    status = _read_string(case.get("status"), "unknown")
    parts = [status]
    if seed:
        parts.append(seed)
    if packs:
        parts.append("packs " + ", ".join(packs[:4]))
    return " · ".join(parts)


def project_cross_pack_evidence_ledger_graph(
    *,
    session_id: str,
    session_node_id: str,
    session_metadata: Mapping[str, Any],
) -> CrossPackEvidenceLedgerProjection:
    ledger = _as_dict(session_metadata.get(LEDGER_METADATA_KEY))
    cases = [_as_dict(item) for item in _as_list(ledger.get("cases"))]
    cases = [case for case in cases if _read_string(case.get("case_id"))]
    projection = CrossPackEvidenceLedgerProjection()
    if not ledger or not cases:
        return projection

    ledger_id = _read_string(ledger.get("ledger_id"), f"ledger-{_short_id(session_id)}")
    ledger_source = _read_string(ledger.get("source"), "host_runtime_session_metadata")
    failed_count = sum(1 for case in cases if _status_for_case(_read_string(case.get("status"))) == "error")
    blocked_count = sum(1 for case in cases if _status_for_case(_read_string(case.get("status"))) == "blocked")
    ledger_status = "error" if failed_count else "blocked" if blocked_count else "ready"
    ledger_node_id = f"cross-pack-ledger-{_safe_id(session_id)}-{_safe_id(ledger_id)}"
    projection.nodes.append(
        MeetingExecutionGraphNode(
            id=ledger_node_id,
            eyebrow="Cross-pack Ledger",
            title=_read_string(ledger.get("title"), "Cross-pack E2E evidence ledger"),
            detail=f"{len(cases)} cases · {ledger_source}",
            status=ledger_status,
            kind="run",
            lane="runs",
            output=_json_output(ledger),
            defaultInspector="trace",
            traceFilter=f"{session_id}:{ledger_id}",
            metadata={
                "projection_source": "cross_pack_evidence_ledger",
                "ledger_id": ledger_id,
                "ledger_source": ledger_source,
                "session_id": session_id,
                "case_count": len(cases),
            },
        )
    )
    projection.edges.append(_edge(session_node_id, ledger_node_id, "contains", "ledger"))

    previous_case_node_id = ledger_node_id
    for index, case in enumerate(cases, start=1):
        case_id = _read_string(case.get("case_id"))
        case_status = _status_for_case(_read_string(case.get("status")))
        case_node_id = f"cross-pack-case-{_safe_id(session_id)}-{_safe_id(case_id)}"
        projection.nodes.append(
            MeetingExecutionGraphNode(
                id=case_node_id,
                eyebrow="E2E Case",
                title=_case_title(case),
                detail=_case_detail(case),
                status=case_status,
                kind="result",
                lane="outputs",
                output=_json_output(case),
                defaultInspector="trace",
                traceFilter=f"{session_id}:{ledger_id}:{case_id}",
                degraded=case_status != "ready",
                metadata={
                    "projection_source": "cross_pack_evidence_ledger",
                    "ledger_id": ledger_id,
                    "ledger_source": ledger_source,
                    "session_id": session_id,
                    "case_id": case_id,
                    "case_index": index,
                    "packs": _as_list(case.get("packs")),
                    "seed": _read_string(case.get("seed")),
                    "prompt_excerpt": _read_string(case.get("prompt_excerpt")),
                    "response_excerpt": _read_string(case.get("response_excerpt")),
                    "artifact_refs": _as_list(case.get("artifact_refs")),
                    "resource_ledger": _as_dict(case.get("resource_ledger")),
                },
            )
        )
        projection.edges.append(_edge(previous_case_node_id, case_node_id, "contains", case_id))
        previous_case_node_id = case_node_id

    return projection


__all__ = [
    "CrossPackEvidenceLedgerProjection",
    "LEDGER_METADATA_KEY",
    "project_cross_pack_evidence_ledger_graph",
]
