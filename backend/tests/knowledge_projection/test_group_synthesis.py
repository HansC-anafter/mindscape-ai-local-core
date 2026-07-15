from types import SimpleNamespace

import pytest

from backend.app.services.knowledge_projection.contracts import (
    AgentClaim,
    GroupSynthesisHandoff,
    GroupSynthesisReceipt,
)
from backend.app.services.knowledge_projection.synthesis import (
    GroupSynthesisPlanner,
)
from backend.app.services.orchestration.dispatch_orchestrator_core.group_synthesis import (
    commit_group_synthesis,
)


def _handoff(claims):
    return GroupSynthesisHandoff(
        run_id="run-1",
        group_id="group-1",
        topology_snapshot_id="snapshot-1",
        policy_revision="policy-v1",
        claims=claims,
    )


def test_synthesis_merges_matching_claims_and_preserves_conflicts():
    claims = [
        AgentClaim(
            agent_id="researcher",
            agent_role="researcher",
            stable_subject_key="topic:retention",
            claim="Retrieval practice improves retention.",
            confidence=0.8,
            evidence_refs=["ev-1"],
        ),
        AgentClaim(
            agent_id="teacher",
            agent_role="teacher",
            stable_subject_key="topic:retention",
            claim="  Retrieval practice improves retention. ",
            confidence=0.9,
            evidence_refs=["ev-2"],
        ),
        AgentClaim(
            agent_id="critic",
            agent_role="critic",
            stable_subject_key="topic:retention",
            claim="Retrieval practice has no measurable effect.",
            confidence=0.6,
            evidence_refs=["ev-3"],
        ),
    ]

    plan = GroupSynthesisPlanner.plan(_handoff(claims))
    reordered = GroupSynthesisPlanner.plan(_handoff(list(reversed(claims))))

    assert plan["input_hash"] == reordered["input_hash"]
    assert len(plan["candidate_rows"]) == 2
    assert len(plan["conflict_sets"]) == 1
    merged = next(row for row in plan["candidate_rows"] if len(row["agent_ids"]) == 2)
    assert merged["agent_ids"] == ["researcher", "teacher"]
    assert merged["evidence_refs"] == ["ev-1", "ev-2"]


@pytest.mark.asyncio
async def test_dispatch_fan_in_invokes_exactly_one_group_committer():
    snapshot = SimpleNamespace(id="snapshot-1", group_id="group-1")

    class _Committer:
        def __init__(self):
            self.handoffs = []

        def commit(self, handoff):
            self.handoffs.append(handoff)
            return GroupSynthesisReceipt(
                receipt_id="receipt-1",
                run_id=handoff.run_id,
                group_id=handoff.group_id,
                topology_snapshot_id=handoff.topology_snapshot_id,
                input_hash="b" * 64,
                status="candidate",
                candidate_memory_ids=["memory-1"],
                conflict_sets=[],
                created=True,
            )

    committer = _Committer()
    orchestrator = SimpleNamespace(
        _group_execution=SimpleNamespace(snapshot=snapshot),
        _group_synthesis_committer=committer,
        _phase_results={
            "phase-b": {
                "group_synthesis_claims": [
                    {
                        "agent_id": "teacher",
                        "agent_role": "teacher",
                        "stable_subject_key": "topic:one",
                        "claim": "Claim one",
                        "evidence_refs": ["ev-1"],
                    }
                ]
            },
            "phase-a": {"execution_id": "not-a-claim"},
        },
    )

    receipt = await commit_group_synthesis(orchestrator, "task-1")

    assert receipt["receipt_id"] == "receipt-1"
    assert len(committer.handoffs) == 1
    assert committer.handoffs[0].run_id == "task-1"
