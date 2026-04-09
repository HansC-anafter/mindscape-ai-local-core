"""
Trace-only round router for meeting deliberation.

Wave 3 goal: produce round routing metadata and events without changing the
existing fixed deliberation order.
"""

import os
from typing import Dict, List, Sequence

from backend.app.models.meeting_round_routing import (
    NeedDescriptor,
    OfferDescriptor,
    RoundGoal,
    RoundRoutingGraph,
    RoutedPacket,
    RoutingEdge,
)


ROUND_ROUTER_TRACE_ENV = "MEETING_DYNAMIC_ROUTING_TRACE_ENABLED"
DYNAMIC_SPARSE_ROUTING_ENV = "MEETING_DYNAMIC_ROUTING_ENABLED"
FIXED_SPEAKER_ORDER = ["facilitator", "planner", "critic"]
ROUND_ROUTING_CONTEXT_WARN_CHARS = 420
ROUND_ROUTING_CONTEXT_COMPRESS_CHARS = 560


def is_round_router_trace_enabled() -> bool:
    """Enable Wave 3 trace-only routing graph emission behind an env flag."""
    return os.getenv(ROUND_ROUTER_TRACE_ENV, "false").strip().lower() == "true"


def is_dynamic_sparse_routing_enabled() -> bool:
    """Enable Wave 4 sparse packet injection for planner/critic turns."""
    return os.getenv(DYNAMIC_SPARSE_ROUTING_ENV, "false").strip().lower() == "true"


def build_round_routing_graph(
    *,
    session_id: str,
    round_number: int,
    agenda: Sequence[str],
    facilitator_summary: str,
    planner_proposals: Sequence[str],
    critic_notes: Sequence[str],
) -> RoundRoutingGraph:
    """Build a deterministic round routing graph for trace and postmortem."""
    goal = RoundGoal(
        round_number=round_number,
        summary=_truncate(facilitator_summary, 220),
        agenda_focus=[_truncate(item, 120) for item in list(agenda)[:5]],
        critical_constraints=_derive_constraints(agenda, facilitator_summary),
    )
    needs = _build_needs(planner_proposals=planner_proposals, critic_notes=critic_notes)
    offers = _build_offers(
        facilitator_summary=facilitator_summary,
        planner_proposals=planner_proposals,
        critic_notes=critic_notes,
    )
    packets = _build_packets(offers)
    edges = _match_edges(needs=needs, packets=packets)

    matched_need_ids = {
        need_id
        for edge in edges
        for need_id in edge.matched_need_ids
    }
    matched_packet_ids = {
        packet_id
        for edge in edges
        for packet_id in edge.packet_ids
    }

    graph = RoundRoutingGraph(
        session_id=session_id,
        round_number=round_number,
        goal=goal,
        needs=needs,
        offers=offers,
        packets=packets,
        edges=edges,
        unmatched_need_ids=[
            need.id for need in needs if need.id not in matched_need_ids
        ],
        unmatched_packet_ids=[
            packet.id for packet in packets if packet.id not in matched_packet_ids
        ],
        fixed_speaker_order=list(FIXED_SPEAKER_ORDER),
        metadata={
            "routing_stage": "deliberation",
            "global_briefing_retained": True,
            "sparse_incremental_packets": True,
            "planner_proposal_count": len(planner_proposals),
            "critic_note_count": len(critic_notes),
            "edge_count": len(edges),
            "packet_count": len(packets),
        },
    )
    graph.metadata.update(
        _build_graph_diagnostics(graph, role_ids=FIXED_SPEAKER_ORDER)
    )
    return graph


def build_executor_routing_graph(
    *,
    session_id: str,
    round_number: int,
    agenda: Sequence[str],
    facilitator_summary: str,
    decision: str,
    planner_proposals: Sequence[str],
    critic_notes: Sequence[str],
) -> RoundRoutingGraph:
    """Build a traceable packet graph for executor action synthesis."""
    goal = RoundGoal(
        round_number=round_number,
        summary=_truncate(
            decision or facilitator_summary or "Synthesize executable action items.",
            220,
        ),
        agenda_focus=[_truncate(item, 120) for item in list(agenda)[:5]],
        critical_constraints=_derive_constraints(agenda, facilitator_summary),
    )
    needs: List[NeedDescriptor] = [
        NeedDescriptor(
            id="executor-global-briefing",
            role_id="executor",
            need_type="global_briefing",
            summary="Executor needs the facilitator's global briefing.",
            source_role_id="facilitator",
        ),
        NeedDescriptor(
            id="executor-decision-draft",
            role_id="executor",
            need_type="decision_draft",
            summary="Executor needs the current decision draft to synthesize action items.",
            source_role_id="facilitator",
        ),
    ]
    if planner_proposals:
        needs.append(
            NeedDescriptor(
                id="executor-latest-plan",
                role_id="executor",
                need_type="planner_proposal",
                summary="Executor needs the latest planner proposal for executable decomposition.",
                source_role_id="planner",
            )
        )
    if critic_notes:
        needs.append(
            NeedDescriptor(
                id="executor-latest-critique",
                role_id="executor",
                need_type="critic_feedback",
                summary="Executor needs the latest critic feedback to avoid known risks.",
                source_role_id="critic",
            )
        )

    offers: List[OfferDescriptor] = [
        OfferDescriptor(
            id="facilitator-global-briefing",
            role_id="facilitator",
            offer_type="global_briefing",
            summary="Facilitator global briefing and round goal.",
            packet_scope="global",
            content_preview=_truncate(facilitator_summary, 180),
        ),
        OfferDescriptor(
            id="facilitator-decision-draft",
            role_id="facilitator",
            offer_type="decision_draft",
            summary="Current decision draft for executor synthesis.",
            packet_scope="sparse",
            content_preview=_truncate(decision, 180),
        ),
    ]
    if planner_proposals:
        offers.append(
            OfferDescriptor(
                id="planner-latest-plan",
                role_id="planner",
                offer_type="planner_proposal",
                summary="Latest planner proposal for executor synthesis.",
                packet_scope="sparse",
                content_preview=_truncate(planner_proposals[-1], 180),
            )
        )
    if critic_notes:
        offers.append(
            OfferDescriptor(
                id="critic-latest-feedback",
                role_id="critic",
                offer_type="critic_feedback",
                summary="Latest critic feedback for executor synthesis.",
                packet_scope="sparse",
                content_preview=_truncate(critic_notes[-1], 180),
            )
        )

    consumer_overrides = {
        "global_briefing": ["executor"],
        "decision_draft": ["executor"],
        "planner_proposal": ["executor"],
        "critic_feedback": ["executor"],
    }
    packets = _build_packets(offers, consumer_overrides=consumer_overrides)
    edges = _match_edges(needs=needs, packets=packets)
    matched_need_ids = {
        need_id
        for edge in edges
        for need_id in edge.matched_need_ids
    }
    matched_packet_ids = {
        packet_id
        for edge in edges
        for packet_id in edge.packet_ids
    }

    graph = RoundRoutingGraph(
        session_id=session_id,
        round_number=round_number,
        goal=goal,
        needs=needs,
        offers=offers,
        packets=packets,
        edges=edges,
        unmatched_need_ids=[
            need.id for need in needs if need.id not in matched_need_ids
        ],
        unmatched_packet_ids=[
            packet.id for packet in packets if packet.id not in matched_packet_ids
        ],
        fixed_speaker_order=list(FIXED_SPEAKER_ORDER),
        metadata={
            "routing_stage": "executor",
            "global_briefing_retained": True,
            "sparse_incremental_packets": True,
            "planner_proposal_count": len(planner_proposals),
            "critic_note_count": len(critic_notes),
            "edge_count": len(edges),
            "packet_count": len(packets),
        },
    )
    graph.metadata.update(_build_graph_diagnostics(graph, role_ids=["executor"]))
    return graph


def _build_needs(
    *,
    planner_proposals: Sequence[str],
    critic_notes: Sequence[str],
) -> List[NeedDescriptor]:
    needs: List[NeedDescriptor] = [
        NeedDescriptor(
            id="planner-global-briefing",
            role_id="planner",
            need_type="global_briefing",
            summary="Planner needs the facilitator's current round briefing.",
            source_role_id="facilitator",
        ),
        NeedDescriptor(
            id="critic-global-briefing",
            role_id="critic",
            need_type="global_briefing",
            summary="Critic needs the facilitator's current round briefing.",
            source_role_id="facilitator",
        ),
    ]
    if planner_proposals:
        needs.append(
            NeedDescriptor(
                id="critic-latest-plan",
                role_id="critic",
                need_type="planner_proposal",
                summary="Critic needs the latest planner proposal for risk review.",
                source_role_id="planner",
            )
        )
        needs.append(
            NeedDescriptor(
                id="facilitator-latest-plan",
                role_id="facilitator",
                need_type="planner_proposal",
                summary="Facilitator needs the latest planner proposal for convergence tracking.",
                source_role_id="planner",
            )
        )
    if critic_notes:
        needs.append(
            NeedDescriptor(
                id="planner-latest-critique",
                role_id="planner",
                need_type="critic_feedback",
                summary="Planner needs the latest critic feedback before refining the plan.",
                source_role_id="critic",
            )
        )
        needs.append(
            NeedDescriptor(
                id="facilitator-latest-critique",
                role_id="facilitator",
                need_type="critic_feedback",
                summary="Facilitator needs the latest critic feedback before deciding convergence.",
                source_role_id="critic",
            )
        )
    return needs


def _build_offers(
    *,
    facilitator_summary: str,
    planner_proposals: Sequence[str],
    critic_notes: Sequence[str],
) -> List[OfferDescriptor]:
    offers: List[OfferDescriptor] = [
        OfferDescriptor(
            id="facilitator-global-briefing",
            role_id="facilitator",
            offer_type="global_briefing",
            summary="Facilitator global briefing and round goal.",
            packet_scope="global",
            content_preview=_truncate(facilitator_summary, 180),
        )
    ]
    if planner_proposals:
        offers.append(
            OfferDescriptor(
                id="planner-latest-plan",
                role_id="planner",
                offer_type="planner_proposal",
                summary="Latest planner proposal for critique and convergence.",
                packet_scope="sparse",
                content_preview=_truncate(planner_proposals[-1], 180),
            )
        )
    if critic_notes:
        offers.append(
            OfferDescriptor(
                id="critic-latest-feedback",
                role_id="critic",
                offer_type="critic_feedback",
                summary="Latest critic feedback for revision and convergence.",
                packet_scope="sparse",
                content_preview=_truncate(critic_notes[-1], 180),
            )
        )
    return offers


def _build_packets(
    offers: Sequence[OfferDescriptor],
    *,
    consumer_overrides: Dict[str, List[str]] | None = None,
) -> List[RoutedPacket]:
    packets: List[RoutedPacket] = []
    for offer in offers:
        consumers = (
            list(consumer_overrides[offer.offer_type])
            if consumer_overrides and offer.offer_type in consumer_overrides
            else _default_consumers_for_offer(offer)
        )
        packets.append(
            RoutedPacket(
                id=f"packet:{offer.id}",
                source_role_id=offer.role_id,
                packet_type=offer.offer_type,
                summary=offer.summary,
                packet_scope=offer.packet_scope,
                consumer_role_ids=consumers,
                content_preview=offer.content_preview,
            )
        )
    return packets


def _default_consumers_for_offer(offer: OfferDescriptor) -> List[str]:
    if offer.offer_type == "global_briefing":
        return ["planner", "critic", "executor"]
    if offer.offer_type == "planner_proposal":
        return ["critic", "facilitator"]
    if offer.offer_type == "critic_feedback":
        return ["planner", "facilitator"]
    return []


def _match_edges(
    *,
    needs: Sequence[NeedDescriptor],
    packets: Sequence[RoutedPacket],
) -> List[RoutingEdge]:
    edge_map: Dict[tuple[str, str], RoutingEdge] = {}
    for need in needs:
        for packet in packets:
            if packet.packet_type != need.need_type:
                continue
            if need.role_id not in packet.consumer_role_ids:
                continue
            key = (packet.source_role_id, need.role_id)
            edge = edge_map.setdefault(
                key,
                RoutingEdge(
                    source_role_id=packet.source_role_id,
                    target_role_id=need.role_id,
                    rationale=_edge_rationale(packet.packet_type, need.role_id),
                ),
            )
            if packet.id not in edge.packet_ids:
                edge.packet_ids.append(packet.id)
            if need.id not in edge.matched_need_ids:
                edge.matched_need_ids.append(need.id)
    return list(edge_map.values())


def packets_for_role(
    graph: RoundRoutingGraph,
    role_id: str,
) -> List[RoutedPacket]:
    """Return routed packets visible to a specific role for this round."""
    matched_packet_ids = {
        packet_id
        for edge in graph.edges
        if edge.target_role_id == role_id
        for packet_id in edge.packet_ids
    }
    visible_packets: List[RoutedPacket] = []
    for packet in graph.packets:
        if role_id not in packet.consumer_role_ids:
            continue
        if packet.packet_scope == "global" or packet.id in matched_packet_ids:
            visible_packets.append(packet)
    return visible_packets


def build_routing_warning_payload(
    graph: RoundRoutingGraph,
) -> Dict[str, object] | None:
    """Summarize routing anomalies into a compact warning payload."""
    metadata = graph.metadata or {}
    next_role_id = str(metadata.get("next_role_id") or "").strip() or None
    starved_role_ids = list(metadata.get("starved_role_ids") or [])
    global_only_role_ids = list(metadata.get("global_only_role_ids") or [])
    largest_context_role_id = metadata.get("largest_context_role_id")
    max_estimated_context_chars = int(metadata.get("max_estimated_context_chars") or 0)

    warning_types: List[str] = []
    summary_parts: List[str] = []
    severity = "medium"

    if starved_role_ids:
        warning_types.append("starved_roles")
        severity = "high"
        summary_parts.append(
            "starved roles: " + ", ".join(_unique_role_ids(starved_role_ids))
        )
    if global_only_role_ids:
        warning_types.append("global_only_roles")
        summary_parts.append(
            "global-only roles: " + ", ".join(_unique_role_ids(global_only_role_ids))
        )
    if (
        largest_context_role_id
        and max_estimated_context_chars >= ROUND_ROUTING_CONTEXT_WARN_CHARS
    ):
        warning_types.append("context_pressure")
        summary_parts.append(
            f"context hot spot: {largest_context_role_id} ~{max_estimated_context_chars} chars"
        )

    if not warning_types:
        return None

    routing_health_status = metadata.get("routing_health_status")
    routing_health_reason = metadata.get("routing_health_reason")
    if not routing_health_status:
        if "starved_roles" in warning_types or metadata.get("routing_prompt_mode") == "full_context_fallback":
            routing_health_status = "critical"
            routing_health_reason = "fallback_pressure"
        elif "context_pressure" in warning_types or metadata.get("routing_prompt_mode") == "compressed_sparse":
            routing_health_status = "warning"
            routing_health_reason = "compression_pressure"
        elif "global_only_roles" in warning_types:
            routing_health_status = "warning"
            routing_health_reason = "fallback_present"

    before_clause = f" before {next_role_id}" if next_role_id else ""
    return {
        "round_number": graph.round_number,
        "routing_stage": metadata.get("routing_stage"),
        "next_role_id": next_role_id,
        "severity": severity,
        "warning_types": warning_types,
        "starved_role_ids": _unique_role_ids(starved_role_ids),
        "global_only_role_ids": _unique_role_ids(global_only_role_ids),
        "diagnostic_flags": list(metadata.get("diagnostic_flags") or []),
        "largest_context_role_id": largest_context_role_id,
        "max_estimated_context_chars": max_estimated_context_chars,
        "routing_prompt_mode": metadata.get("routing_prompt_mode"),
        "routing_prompt_reason": metadata.get("routing_prompt_reason"),
        "routing_prompt_role_id": metadata.get("routing_prompt_role_id"),
        "routing_health_status": routing_health_status,
        "routing_health_reason": routing_health_reason,
        "compressed_packet_char_limit": metadata.get("compressed_packet_char_limit"),
        "summary": f"Routing warning{before_clause}: " + "; ".join(summary_parts),
    }


def _build_graph_diagnostics(
    graph: RoundRoutingGraph,
    *,
    role_ids: Sequence[str],
) -> Dict[str, object]:
    ordered_role_ids = _unique_role_ids(role_ids)
    role_packet_stats: Dict[str, Dict[str, object]] = {}
    starved_role_ids: List[str] = []
    global_only_role_ids: List[str] = []
    diagnostic_flags: List[str] = []
    largest_context_role_id: str | None = None
    max_estimated_context_chars = 0

    for role_id in ordered_role_ids:
        role_needs = [need for need in graph.needs if need.role_id == role_id]
        required_needs = [need for need in role_needs if need.required]
        incremental_needs = [
            need for need in required_needs if need.need_type != "global_briefing"
        ]
        visible_packets = packets_for_role(graph, role_id)
        unmatched_required_need_ids = [
            need.id for need in required_needs if need.id in graph.unmatched_need_ids
        ]
        global_packet_count = sum(
            1 for packet in visible_packets if packet.packet_scope == "global"
        )
        sparse_packet_count = sum(
            1 for packet in visible_packets if packet.packet_scope == "sparse"
        )
        estimated_context_chars = sum(
            _estimate_packet_chars(packet) for packet in visible_packets
        )

        if unmatched_required_need_ids:
            status = "starved"
            starved_role_ids.append(role_id)
            diagnostic_flags.append(f"{role_id}:unmatched_required")
        elif not visible_packets and required_needs:
            status = "starved"
            starved_role_ids.append(role_id)
            diagnostic_flags.append(f"{role_id}:no_visible_packets")
        elif not visible_packets:
            status = "idle"
        elif sparse_packet_count == 0 and incremental_needs:
            status = "global_only"
            global_only_role_ids.append(role_id)
            diagnostic_flags.append(f"{role_id}:global_only")
        else:
            status = "healthy"

        role_packet_stats[role_id] = {
            "status": status,
            "visible_packet_count": len(visible_packets),
            "global_packet_count": global_packet_count,
            "sparse_packet_count": sparse_packet_count,
            "matched_need_count": len(role_needs) - len(
                [need for need in role_needs if need.id in graph.unmatched_need_ids]
            ),
            "required_need_count": len(required_needs),
            "incremental_need_count": len(incremental_needs),
            "unmatched_required_need_count": len(unmatched_required_need_ids),
            "unmatched_required_need_ids": unmatched_required_need_ids,
            "estimated_context_chars": estimated_context_chars,
            "visible_packet_types": [packet.packet_type for packet in visible_packets],
            "visible_packet_ids": [packet.id for packet in visible_packets],
        }
        if estimated_context_chars >= max_estimated_context_chars:
            max_estimated_context_chars = estimated_context_chars
            largest_context_role_id = role_id

    return {
        "role_count": len(role_packet_stats),
        "role_packet_stats": role_packet_stats,
        "starved_role_ids": starved_role_ids,
        "global_only_role_ids": global_only_role_ids,
        "diagnostic_flags": diagnostic_flags,
        "largest_context_role_id": largest_context_role_id,
        "max_estimated_context_chars": max_estimated_context_chars,
    }


def _edge_rationale(packet_type: str, target_role_id: str) -> str:
    if packet_type == "global_briefing":
        return f"Global briefing is retained for {target_role_id}."
    if packet_type == "planner_proposal":
        return f"Latest planner proposal is routed to {target_role_id} for critique/convergence."
    if packet_type == "critic_feedback":
        return f"Latest critic feedback is routed to {target_role_id} for revision/convergence."
    return f"Packet routed to {target_role_id}."


def _derive_constraints(
    agenda: Sequence[str],
    facilitator_summary: str,
) -> List[str]:
    constraints = [item.strip() for item in agenda if item.strip()][:3]
    summary = facilitator_summary.lower()
    if "risk" in summary:
        constraints.append("Risk mitigation must remain visible.")
    if "tool" in summary:
        constraints.append("Available tool inventory must remain grounded.")
    return constraints[:4]


def _truncate(value: str, limit: int) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _estimate_packet_chars(packet: RoutedPacket) -> int:
    return len((packet.content_preview or packet.summary or "").strip())


def _unique_role_ids(role_ids: Sequence[str]) -> List[str]:
    ordered_role_ids: List[str] = []
    for role_id in role_ids:
        if role_id and role_id not in ordered_role_ids:
            ordered_role_ids.append(role_id)
    return ordered_role_ids
