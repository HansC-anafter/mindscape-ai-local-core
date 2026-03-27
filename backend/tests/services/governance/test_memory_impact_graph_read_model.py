from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.services.governance.memory_impact_graph_read_model import (
    MemoryImpactGraphReadModel,
)


class StubMeetingSessionStore:
    def __init__(self, sessions=None, decisions_by_session=None):
        self.sessions = {session.id: session for session in list(sessions or [])}
        self.decisions_by_session = dict(decisions_by_session or {})

    def get_by_id(self, session_id):
        return self.sessions.get(session_id)

    def list_by_workspace(self, workspace_id, project_id=None, limit=100, offset=0):
        sessions = [
            session
            for session in self.sessions.values()
            if session.workspace_id == workspace_id
            and (project_id is None or session.project_id == project_id)
        ]
        sessions.sort(key=lambda session: session.started_at, reverse=True)
        return sessions[offset : offset + limit]

    def list_decisions_by_session(self, session_id):
        return list(self.decisions_by_session.get(session_id, []))


class StubMemoryItemStore:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def get(self, item_id):
        return self.items.get(item_id)


def _build_session():
    return MeetingSession(
        id="sess-1",
        workspace_id="ws-1",
        project_id="proj-1",
        thread_id="thread-1",
        started_at=datetime(2026, 3, 26, 6, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 26, 6, 10, tzinfo=timezone.utc),
        status=MeetingStatus.CLOSED,
        meeting_type="planning",
        round_count=1,
        action_items=[
            {
                "title": "Run review pass",
                "description": "Execute artifact review",
                "assigned_to": "executor",
                "landing_status": "launched",
                "execution_id": "exec-1",
                "asset_refs": ["artifact-1"],
            }
        ],
        metadata={
            "execution_ids": ["exec-1"],
            "selected_memory_packet": {
                "selection": {"workspace_mode": "meeting", "memory_scope": "extended"},
                "route_plan": ["core", "verified_knowledge", "episodic_evidence"],
                "layers": {
                    "core": {
                        "brand_identity": "Mindscape",
                        "voice_and_tone": "direct",
                    },
                    "knowledge": {
                        "verified": [
                            {
                                "id": "kn-1",
                                "knowledge_type": "constraint",
                                "content": "Preserve deterministic UI audit output",
                                "status": "verified",
                            }
                        ],
                        "candidates": [],
                    },
                    "goals": {
                        "active": [
                            {
                                "id": "goal-1",
                                "title": "Ship memory visibility",
                                "description": "Operator can inspect memory impact",
                                "status": "active",
                            }
                        ],
                        "pending": [],
                    },
                    "episodic": [
                        {
                            "id": "mem-episodic-1",
                            "title": "Previous audit session",
                            "summary": "Audit found missing impact trace.",
                            "claim": "Audit found missing impact trace.",
                            "lifecycle_status": "active",
                            "verification_status": "verified",
                        }
                    ],
                    "project": None,
                    "member": None,
                },
            },
            "selected_memory_packet_node_ids": [
                "workspace_core:ws-1",
                "knowledge:kn-1",
                "goal:goal-1",
                "memory_item:mem-episodic-1",
            ],
            "canonical_memory": {
                "memory_item_id": "mem-writeback-1",
                "digest_id": "digest-1",
                "writeback_run_id": "run-1",
                "lifecycle_status": "candidate",
                "verification_status": "observed",
            },
            "memory_impact_trace": {
                "explicit": {
                    "session_node_id": "meeting_session:sess-1",
                    "selected_packet_node_ids": [
                        "workspace_core:ws-1",
                        "knowledge:kn-1",
                        "goal:goal-1",
                        "memory_item:mem-episodic-1",
                    ],
                    "meeting_decision_node_ids": ["meeting_decision:dec-1"],
                    "action_item_node_ids": ["action_item:sess-1:0"],
                    "canonical_writeback_node_id": "memory_item:mem-writeback-1",
                    "digest_node_id": "session_digest:digest-1",
                    "writeback_run_id": "run-1",
                },
                "inferred": None,
            },
        },
    )


def test_memory_impact_graph_read_model_builds_selected_subgraph():
    session = _build_session()
    store = StubMeetingSessionStore(
        sessions=[session],
        decisions_by_session={
            session.id: [
                MeetingDecision(
                    id="dec-1",
                    session_id=session.id,
                    workspace_id=session.workspace_id,
                    category="decision",
                    content="Use a task-centered memory subgraph first.",
                    status="pending",
                    source_action_item={"execution_id": "exec-1"},
                )
            ]
        },
    )
    memory_item_store = StubMemoryItemStore(
        items={
            "mem-writeback-1": SimpleNamespace(
                id="mem-writeback-1",
                title="Meeting episode sess-1",
                summary="Closure recorded selected packet and writeback lineage.",
                claim="Closure recorded selected packet and writeback lineage.",
            )
        }
    )
    read_model = MemoryImpactGraphReadModel(
        meeting_session_store=store,
        memory_item_store=memory_item_store,
    )

    response = read_model.build_for_workspace("ws-1", session_id="sess-1")

    assert response.workspace_id == "ws-1"
    assert response.session_id == "sess-1"
    assert response.packet_summary.selected_node_count == 4
    assert response.packet_summary.route_sections == [
        "core",
        "verified_knowledge",
        "episodic_evidence",
    ]
    node_types = {node.id: node.type for node in response.nodes}
    assert node_types["meeting_session:sess-1"] == "session"
    assert node_types["execution:exec-1"] == "execution"
    assert node_types["knowledge:kn-1"] == "knowledge"
    assert node_types["goal:goal-1"] == "goal"
    assert node_types["memory_item:mem-writeback-1"] == "memory_item"
    assert node_types["session_digest:digest-1"] == "digest"
    assert node_types["artifact:artifact-1"] == "artifact"

    edge_index = {(edge.kind, edge.from_node_id, edge.to_node_id) for edge in response.edges}
    assert (
        "selected_for_context",
        "meeting_session:sess-1",
        "knowledge:kn-1",
    ) in edge_index
    assert (
        "writes_back_to",
        "meeting_session:sess-1",
        "memory_item:mem-writeback-1",
    ) in edge_index
    assert (
        "derived_from",
        "memory_item:mem-writeback-1",
        "session_digest:digest-1",
    ) in edge_index
    assert ("produced", "action_item:sess-1:0", "execution:exec-1") in edge_index


def test_memory_impact_graph_read_model_resolves_session_by_execution_id():
    session = _build_session()
    read_model = MemoryImpactGraphReadModel(
        meeting_session_store=StubMeetingSessionStore(sessions=[session]),
        memory_item_store=StubMemoryItemStore(),
    )

    response = read_model.build_for_workspace("ws-1", execution_id="exec-1")

    assert response.session_id == "sess-1"
    assert response.focus.execution_id == "exec-1"
