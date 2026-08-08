from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.models.guided_learning_contract import (
    GuidedLearningContext,
    GuidedLearningRoute,
)
from backend.app.models.request_contract import (
    GroundedKnowledgeAnswerRequest,
    RequestContract,
)
from backend.app.services.orchestration.meeting.knowledge_answer.citation_verifier import (
    GroundedAnswerCitationVerifier,
)
from backend.app.services.orchestration.meeting.knowledge_answer.facade import (
    GroundedKnowledgeAnswerFacade,
)
from backend.app.services.orchestration.meeting.knowledge_answer.plan_compiler import (
    GroundedKnowledgeAnswerPlanCompiler,
)
from backend.app.services.orchestration.meeting.meeting_command_authority import (
    build_internal_workspace_authority,
)


class _QueryPort:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []

    async def execute(self, operation, *, authority):
        self.calls.append((operation, authority))
        return self.results.pop(0)


class _LLM:
    async def chat_completion(self, messages, **kwargs):
        return (
            '{"claims":[{"text":"Birds are theropod dinosaurs.",'
            '"citation_ids":["external_doc:bird-1"]}],'
            '"uncertainties":[],"safety_notes":[]}'
        )


def _contract(*, modes=("hybrid",), guided=False) -> RequestContract:
    return RequestContract(
        goals=["Explain the evolutionary relationship."],
        source_message="Why are birds living dinosaurs?",
        workspace_scope="ws_demo",
        grounded_knowledge_answer=GroundedKnowledgeAnswerRequest(
            question="Why are birds living dinosaurs?",
            retrieval_modes=modes,
            scope="workspace",
            guided_learning_context=(
                GuidedLearningContext(
                    current_question_id="q:birds-dinosaurs",
                    current_checkpoint_id="checkpoint:ancestry",
                    current_competency_key=(
                        "question_checkpoint:ancestry"
                    ),
                    belief_uncertainty=0.62,
                    due_state="not_due",
                    session_state="explore",
                    why_this_next=(
                        "先區分共同祖先與物種專屬 DNA。"
                    ),
                    next_routes=[
                        GuidedLearningRoute(
                            route_id="route:prerequisite",
                            question_id="q:shared-ancestry",
                            label="先補共同祖先",
                            route_kind="prerequisite",
                        ),
                        GuidedLearningRoute(
                            route_id="route:evidence",
                            question_id="q:evidence",
                            label="檢查證據種類",
                            route_kind="branch",
                        ),
                    ],
                )
                if guided
                else None
            ),
        ),
    )


def _authority():
    return build_internal_workspace_authority(
        workspace_id="ws_demo",
        workspace_owner_user_id="profile_demo",
        active_group_id=None,
        command_id="cmd_demo",
    )


def test_plan_compiler_preserves_explicit_bounded_modes():
    plan = GroundedKnowledgeAnswerPlanCompiler().compile(
        _contract(modes=("local_graph", "multi_hop"))
    )
    assert plan is not None
    assert [item.retrieval_mode for item in plan.operations] == [
        "local_graph",
        "multi_hop",
    ]
    assert all(item.operation == "search" for item in plan.operations)


def test_citation_verifier_rejects_unadmitted_citation():
    with pytest.raises(
        ValueError,
        match="grounded_answer_citation_not_admitted",
    ):
        GroundedAnswerCitationVerifier().verify(
            synthesis={
                "claims": [
                    {
                        "text": "Unsupported",
                        "citation_ids": ["external_doc:unknown"],
                    }
                ]
            },
            citations=[
                {
                    "citation_id": "external_doc:known",
                    "content_hash": "a" * 64,
                }
            ],
        )


@pytest.mark.asyncio
async def test_facade_answers_once_and_projects_only_compact_evidence_refs():
    query_port = _QueryPort(
        [
            {
                "evidence": [
                    {
                        "content": "Bird fossils connect birds to theropods.",
                        "source_kind": "document",
                        "source_id": "bird-1",
                        "title": "Bird evolution",
                        "modality": "text",
                        "citation": {
                            "citation_id": "external_doc:bird-1",
                            "content_hash": "a" * 64,
                        },
                    }
                ],
                "coverage": {"mode": "hybrid", "candidate_count": 1},
                "_meeting_admission_snapshot_hash": "b" * 64,
            }
        ]
    )
    result = await GroundedKnowledgeAnswerFacade(
        query_port=query_port,
    ).answer(
        contract=_contract(),
        authority=_authority(),
        llm=_LLM(),
    )

    assert result is not None
    assert result.status == "answered"
    assert result.receipt["tool_call_count"] == 1
    assert result.receipt["synthesis_call_count"] == 1
    assert result.receipt["verification_status"] == "passed"
    assert result.claims[0].citation_ids == ("external_doc:bird-1",)
    assert "content" not in result.evidence_refs[0]
    assert result.evidence_refs[0]["source_id"] == "bird-1"
    assert len(query_port.calls) == 1


@pytest.mark.asyncio
async def test_guided_answer_projects_one_action_and_three_or_fewer_routes():
    result = await GroundedKnowledgeAnswerFacade(
        query_port=_QueryPort(
            [
                {
                    "evidence": [
                        {
                            "content": "Birds descend from theropods.",
                            "source_kind": "document",
                            "source_id": "bird-1",
                            "title": "Bird evolution",
                            "modality": "text",
                            "citation": {
                                "citation_id": "external_doc:bird-1",
                                "content_hash": "a" * 64,
                            },
                        }
                    ],
                    "coverage": {"mode": "hybrid"},
                    "_meeting_admission_snapshot_hash": "b" * 64,
                }
            ]
        )
    ).answer(
        contract=_contract(guided=True),
        authority=_authority(),
        llm=_LLM(),
    )
    assert result.guided_learning is not None
    assert result.guided_learning.pedagogical_action == "probe"
    assert len(result.guided_learning.route_choices) == 2
    assert result.guided_learning.writes_mastery is False


@pytest.mark.asyncio
async def test_facade_returns_insufficient_evidence_without_llm_call():
    class _ForbiddenLLM:
        async def chat_completion(self, messages, **kwargs):
            raise AssertionError("LLM must not run without evidence")

    result = await GroundedKnowledgeAnswerFacade(
        query_port=_QueryPort(
            [
                {
                    "evidence": [],
                    "coverage": {"mode": "hybrid", "candidate_count": 0},
                    "_meeting_admission_snapshot_hash": "c" * 64,
                }
            ]
        )
    ).answer(
        contract=_contract(),
        authority=_authority(),
        llm=_ForbiddenLLM(),
    )
    assert result is not None
    assert result.status == "insufficient_evidence"
    assert result.receipt["synthesis_call_count"] == 0
