import pytest

from backend.app.services.orchestration.meeting.round_router import (
    build_executor_routing_graph,
    build_routing_warning_payload,
    DYNAMIC_SPARSE_ROUTING_ENV,
    ROUND_ROUTER_TRACE_ENV,
    build_round_routing_graph,
    is_round_router_trace_enabled,
    is_dynamic_sparse_routing_enabled,
    packets_for_role,
)


def test_build_round_routing_graph_keeps_global_briefing_and_sparse_edges() -> None:
    graph = build_round_routing_graph(
        session_id="session-1",
        round_number=2,
        agenda=["Ship the handoff flow", "Keep risk visible"],
        facilitator_summary=(
            "Focus this round on a shippable compile path while keeping tool and risk "
            "constraints visible to every role."
        ),
        planner_proposals=[
            "1. Accept compile job. 2. Persist session linkage. 3. Verify writeback."
        ],
        critic_notes=[
            "Risk: restart recovery may fail without durable ownership. Mitigation: reconcile pending jobs."
        ],
    )

    global_packet = next(
        packet for packet in graph.packets if packet.packet_type == "global_briefing"
    )
    assert global_packet.packet_scope == "global"
    assert set(global_packet.consumer_role_ids) == {"planner", "critic", "executor"}

    edges = {(edge.source_role_id, edge.target_role_id): edge for edge in graph.edges}
    assert ("facilitator", "planner") in edges
    assert ("facilitator", "critic") in edges
    assert ("planner", "critic") in edges
    assert ("critic", "planner") in edges
    assert ("planner", "facilitator") in edges
    assert ("critic", "facilitator") in edges

    assert graph.goal.summary.startswith("Focus this round")
    assert graph.metadata["global_briefing_retained"] is True
    assert graph.metadata["sparse_incremental_packets"] is True
    assert graph.metadata["starved_role_ids"] == []
    assert graph.metadata["global_only_role_ids"] == []
    planner_stats = graph.metadata["role_packet_stats"]["planner"]
    critic_stats = graph.metadata["role_packet_stats"]["critic"]
    facilitator_stats = graph.metadata["role_packet_stats"]["facilitator"]
    assert planner_stats["status"] == "healthy"
    assert planner_stats["visible_packet_types"] == ["global_briefing", "critic_feedback"]
    assert planner_stats["estimated_context_chars"] > 0
    assert critic_stats["status"] == "healthy"
    assert critic_stats["visible_packet_types"] == ["global_briefing", "planner_proposal"]
    assert facilitator_stats["visible_packet_types"] == [
        "planner_proposal",
        "critic_feedback",
    ]
    assert graph.metadata["max_estimated_context_chars"] >= planner_stats[
        "estimated_context_chars"
    ]
    assert graph.unmatched_need_ids == []
    assert graph.unmatched_packet_ids == []


def test_build_round_routing_graph_stays_minimal_without_prior_turns() -> None:
    graph = build_round_routing_graph(
        session_id="session-2",
        round_number=1,
        agenda=["Draft the first plan"],
        facilitator_summary="Round one goal: establish the initial plan and keep everyone aligned.",
        planner_proposals=[],
        critic_notes=[],
    )

    assert [packet.packet_type for packet in graph.packets] == ["global_briefing"]
    assert {(edge.source_role_id, edge.target_role_id) for edge in graph.edges} == {
        ("facilitator", "planner"),
        ("facilitator", "critic"),
    }
    assert graph.unmatched_need_ids == []
    assert graph.unmatched_packet_ids == []
    assert graph.fixed_speaker_order == ["facilitator", "planner", "critic"]
    assert graph.metadata["starved_role_ids"] == []
    assert graph.metadata["global_only_role_ids"] == []
    assert graph.metadata["role_packet_stats"]["facilitator"]["status"] == "idle"
    assert graph.metadata["role_packet_stats"]["planner"]["status"] == "healthy"
    assert graph.metadata["role_packet_stats"]["planner"]["visible_packet_types"] == [
        "global_briefing"
    ]
    assert graph.metadata["role_packet_stats"]["critic"]["status"] == "healthy"


def test_packets_for_role_keep_global_briefing_but_sparse_incremental_delta() -> None:
    graph = build_round_routing_graph(
        session_id="session-3",
        round_number=3,
        agenda=["Finalize plan"],
        facilitator_summary="Use the current round to converge the plan and keep risk mitigation explicit.",
        planner_proposals=["Planner proposal for this round"],
        critic_notes=["Critic concern from the prior round"],
    )

    planner_packets = packets_for_role(graph, "planner")
    critic_packets = packets_for_role(graph, "critic")

    assert [packet.packet_type for packet in planner_packets] == [
        "global_briefing",
        "critic_feedback",
    ]
    assert [packet.packet_type for packet in critic_packets] == [
        "global_briefing",
        "planner_proposal",
    ]


def test_build_executor_routing_graph_routes_supplement_packets_to_executor() -> None:
    graph = build_executor_routing_graph(
        session_id="session-4",
        round_number=3,
        agenda=["Finalize plan"],
        facilitator_summary="Converge the plan and translate it into executable action items.",
        decision="Ship the async compile path with job/session-first polling.",
        planner_proposals=["Planner proposal for executor"],
        critic_notes=["Critic risk note for executor"],
    )

    assert graph.metadata["routing_stage"] == "executor"
    assert {(edge.source_role_id, edge.target_role_id) for edge in graph.edges} == {
        ("facilitator", "executor"),
        ("planner", "executor"),
        ("critic", "executor"),
    }
    assert [packet.packet_type for packet in packets_for_role(graph, "executor")] == [
        "global_briefing",
        "decision_draft",
        "planner_proposal",
        "critic_feedback",
    ]
    executor_stats = graph.metadata["role_packet_stats"]["executor"]
    assert executor_stats["status"] == "healthy"
    assert executor_stats["visible_packet_count"] == 4
    assert executor_stats["sparse_packet_count"] == 3
    assert graph.metadata["largest_context_role_id"] == "executor"
    assert graph.unmatched_need_ids == []
    assert graph.unmatched_packet_ids == []


def test_build_routing_warning_payload_reports_context_pressure() -> None:
    graph = build_executor_routing_graph(
        session_id="session-5",
        round_number=4,
        agenda=["Finalize plan"],
        facilitator_summary="A" * 800,
        decision="B" * 800,
        planner_proposals=["C" * 800],
        critic_notes=["D" * 800],
    )
    graph.metadata["next_role_id"] = "executor"
    graph.metadata["routing_prompt_mode"] = "compressed_sparse"
    graph.metadata["routing_prompt_reason"] = "context_pressure"
    graph.metadata["routing_prompt_role_id"] = "executor"
    graph.metadata["compressed_packet_char_limit"] = 96

    warning = build_routing_warning_payload(graph)

    assert warning is not None
    assert warning["severity"] == "medium"
    assert warning["warning_types"] == ["context_pressure"]
    assert warning["largest_context_role_id"] == "executor"
    assert warning["max_estimated_context_chars"] >= 420
    assert warning["routing_prompt_mode"] == "compressed_sparse"
    assert warning["routing_prompt_reason"] == "context_pressure"
    assert warning["routing_prompt_role_id"] == "executor"
    assert warning["routing_health_status"] == "warning"
    assert warning["routing_health_reason"] == "compression_pressure"
    assert warning["compressed_packet_char_limit"] == 96
    assert "before executor" in str(warning["summary"])


def test_build_routing_warning_payload_reports_starvation_and_global_only() -> None:
    graph = build_round_routing_graph(
        session_id="session-6",
        round_number=2,
        agenda=["Investigate routing risk"],
        facilitator_summary="Keep sparse routing grounded.",
        planner_proposals=["Planner proposal"],
        critic_notes=["Critic feedback"],
    )
    graph.metadata["next_role_id"] = "planner"
    graph.metadata["starved_role_ids"] = ["planner"]
    graph.metadata["global_only_role_ids"] = ["critic"]
    graph.metadata["diagnostic_flags"] = [
        "planner:unmatched_required",
        "critic:global_only",
    ]

    warning = build_routing_warning_payload(graph)

    assert warning is not None
    assert warning["severity"] == "high"
    assert warning["warning_types"] == ["starved_roles", "global_only_roles"]
    assert warning["starved_role_ids"] == ["planner"]
    assert warning["global_only_role_ids"] == ["critic"]
    assert warning["routing_prompt_mode"] is None
    assert warning["routing_health_status"] == "critical"
    assert warning["routing_health_reason"] == "fallback_pressure"
    assert "starved roles: planner" in str(warning["summary"])
    assert "global-only roles: critic" in str(warning["summary"])


def test_round_router_trace_flag_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ROUND_ROUTER_TRACE_ENV, "true")
    assert is_round_router_trace_enabled() is True

    monkeypatch.setenv(ROUND_ROUTER_TRACE_ENV, "false")
    assert is_round_router_trace_enabled() is False


def test_dynamic_sparse_routing_flag_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DYNAMIC_SPARSE_ROUTING_ENV, "true")
    assert is_dynamic_sparse_routing_enabled() is True

    monkeypatch.setenv(DYNAMIC_SPARSE_ROUTING_ENV, "false")
    assert is_dynamic_sparse_routing_enabled() is False
