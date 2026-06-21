from types import SimpleNamespace

import pytest

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.drift_report import DriftScores
from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.services.egb_orchestrator import EGBOrchestrator
from backend.app.egb.services.egb_orchestrator_drift import (
    compute_semantic_diff_pointers,
)


def _correlation(run_id: str) -> CorrelationIds:
    return CorrelationIds(
        workspace_id="workspace-1",
        intent_id="intent-1",
        decision_id="decision-1",
        playbook_id="playbook-1",
        run_id=run_id,
        policy_version="policy-1",
    )


def _evidence(run_id: str, hashes: dict[str, str]) -> StructuredEvidence:
    return StructuredEvidence(
        evidence_id=f"evidence-{run_id}",
        run_id=run_id,
        workspace_id="workspace-1",
        intent_id="intent-1",
        key_fields_hash_map=hashes,
    )


class FakeTraceLinker:
    def __init__(self, runs):
        self.runs = runs

    async def get_run_by_id(self, run_id):
        return self.runs.get(run_id)

    async def register_run(self, correlation_ids):
        return SimpleNamespace(success=True, error=None)


class FakeDriftScorer:
    def __init__(self):
        self.calls = []

    async def compute_drift(self, *, current, baseline, store):
        self.calls.append((current.run_id, baseline.run_id, store))
        return DriftScores(semantic_drift=0.5)


class FakePolicyAttributor:
    async def attribute_drift(self, *, drift_scores, current_evidence, baseline_evidence):
        return []


class FakeEvidenceReducer:
    def __init__(self):
        self.calls = []

    async def reduce_trace(self, *, trace, correlation_ids):
        self.calls.append((trace, correlation_ids.run_id))
        return _evidence(correlation_ids.run_id, {})


class FakeStore:
    def __init__(self):
        self.saved_reports = []

    async def save_drift_report(self, drift_report):
        self.saved_reports.append(drift_report)


def test_compute_semantic_diff_pointers_compares_union_keys():
    current = _evidence("current", {"/same": "a", "/changed": "b", "/new": "c"})
    baseline = _evidence("baseline", {"/same": "a", "/changed": "old", "/old": "z"})

    assert sorted(compute_semantic_diff_pointers(current, baseline)) == [
        "/changed",
        "/new",
        "/old",
    ]


@pytest.mark.asyncio
async def test_get_drift_report_uses_fake_store_without_live_resources():
    current_ids = _correlation("run-current")
    baseline_ids = _correlation("run-baseline")
    store = FakeStore()
    drift_scorer = FakeDriftScorer()
    orchestrator = EGBOrchestrator(
        trace_linker=FakeTraceLinker(
            {"run-current": current_ids, "run-baseline": baseline_ids}
        ),
        evidence_reducer=FakeEvidenceReducer(),
        drift_scorer=drift_scorer,
        policy_attributor=FakePolicyAttributor(),
        lens_explainer=SimpleNamespace(),
        governance_tuner=SimpleNamespace(),
        store=store,
    )
    orchestrator._evidence_cache["run-current"] = _evidence(
        "run-current", {"/field": "current"}
    )
    orchestrator._evidence_cache["run-baseline"] = _evidence(
        "run-baseline", {"/field": "baseline"}
    )

    report = await orchestrator.get_drift_report(
        "run-current", baseline_run_id="run-baseline"
    )

    assert report.run_id == "run-current"
    assert report.baseline_run_id == "run-baseline"
    assert report.semantic_diff_pointers == ["/field"]
    assert store.saved_reports == [report]
    assert drift_scorer.calls == [("run-current", "run-baseline", store)]


@pytest.mark.asyncio
async def test_rebuild_evidence_no_adapter_returns_none_without_network():
    reducer = FakeEvidenceReducer()
    orchestrator = EGBOrchestrator(
        trace_linker=FakeTraceLinker({}),
        evidence_reducer=reducer,
        drift_scorer=FakeDriftScorer(),
        policy_attributor=FakePolicyAttributor(),
        lens_explainer=SimpleNamespace(),
        governance_tuner=SimpleNamespace(),
        store=FakeStore(),
        langfuse_adapter=None,
    )

    assert await orchestrator._rebuild_evidence("run-missing", _correlation("run-missing")) is None
    assert reducer.calls == []
