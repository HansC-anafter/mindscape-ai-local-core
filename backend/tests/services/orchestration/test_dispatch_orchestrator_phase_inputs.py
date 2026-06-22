"""Phase input normalization tests for DispatchOrchestrator."""

import pytest

from backend.tests.services.orchestration.dispatch_orchestrator_test_support import (
    FakePhaseIR,
    FakeSession,
    FakeTaskIR,
    make_fake_dispatch_orchestrator,
)


class TestPhaseInputNormalization:
    """Deterministic hydration for weakly-specified meeting phases."""

    @pytest.mark.asyncio
    async def test_process_papers_pipeline_derives_query_from_dependencies(self):
        orch = make_fake_dispatch_orchestrator(session=FakeSession(), profile_id="user-1")
        phases = [
            FakePhaseIR(
                id="fetch_a",
                name="Fetch A",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 1},
            ),
            FakePhaseIR(
                id="fetch_b",
                name="Fetch B",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 9},
            ),
            FakePhaseIR(
                id="process",
                name="Process",
                tool_name="frontier_research.process_papers_pipeline",
                depends_on=["fetch_a", "fetch_b"],
                input_params={},
            ),
        ]

        await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=[
                {"title": "Fetch A"},
                {"title": "Fetch B"},
                {"title": "Process"},
            ],
        )

        assert phases[2].input_params["query"] == "autonomic nervous system"
        assert phases[2].input_params["max_results"] == 10

    @pytest.mark.asyncio
    async def test_article_draft_hydrates_workspace_topic_and_ig_format(self):
        session = FakeSession(workspace_id="ws-yoga")
        orch = make_fake_dispatch_orchestrator(session=session, profile_id="user-1")
        phases = [
            FakePhaseIR(
                id="fetch",
                name="Fetch",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 3},
            ),
            FakePhaseIR(
                id="draft",
                name="Generate IG Post Drafts",
                preferred_engine="playbook:article_draft",
                depends_on=["fetch"],
                input_params={
                    "post_count": 3,
                    "source_uri": "artifact://phase_4/output.pdf",
                },
            ),
        ]

        await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=[{"title": "Fetch"}, {"title": "Generate IG Post Drafts"}],
        )

        assert phases[1].input_params["topic"] == "autonomic nervous system"
        assert phases[1].input_params["workspace_id"] == "ws-yoga"
        assert phases[1].input_params["sources"] == ["pubmed", "semantic_scholar"]
        assert phases[1].input_params["language"] == "zh-TW"
        assert phases[1].input_params["target_format"] == "ig_caption"
