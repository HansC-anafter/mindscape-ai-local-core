from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TOUCHED_FILES = [
    "backend/app/services/memory/writeback/meeting_memory_writeback_orchestrator.py",
    "backend/app/services/memory/writeback/meeting_memory_writeback/__init__.py",
    "backend/app/services/memory/writeback/meeting_memory_writeback/collectors.py",
    "backend/app/services/memory/writeback/meeting_memory_writeback/evidence_links.py",
    "backend/app/services/memory/writeback/meeting_memory_writeback/projections.py",
    "backend/tests/meeting_memory_writeback_orchestrator_seams_spec.py",
]

PRODUCTION_FILES = [path for path in TOUCHED_FILES if not path.startswith("backend/tests/")]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_canonical_lifecycle_caller_still_uses_orchestrator_facade():
    source = read_source(
        "backend/app/services/orchestration/meeting/session_core/lifecycle_mixin.py"
    )
    assert "meeting_memory_writeback_orchestrator" in source
    assert "MeetingMemoryWritebackOrchestrator" in source
    assert "run_for_closed_session" in source


def test_facade_keeps_public_and_private_wrapper_contracts():
    source = read_source(
        "backend/app/services/memory/writeback/meeting_memory_writeback_orchestrator.py"
    )
    for fragment in [
        "class MeetingMemoryWritebackOrchestrator",
        "def run_for_closed_session",
        "def _safe_dispatch_legacy_projection",
        "def _safe_dispatch_metadata_projection",
        "def _collect_phase2_evidence",
        "def _safe_attach_reasoning_trace_evidence",
        "def _safe_attach_lens_receipt_evidence",
        "def _safe_attach_writeback_receipt_evidence",
        "def _safe_attach_task_execution_evidence",
        "def _safe_attach_artifact_result_evidence",
        "def _safe_attach_meeting_decision_evidence",
        "self.run_store.mark_stage",
        "self.run_store.mark_completed",
        "self.run_store.mark_failed",
    ]:
        assert fragment in source

    moved_fragments = [
        "MemoryEvidenceLink.from_reasoning_trace",
        "MemoryEvidenceLink.from_lens_receipt",
        "MemoryEvidenceLink.from_writeback_receipt",
        "MemoryEvidenceLink.from_task_execution",
        "MemoryEvidenceLink.from_artifact_result",
        "MemoryEvidenceLink.from_meeting_decision",
        "legacy_projection_adapter.dispatch_digest_projection",
        "metadata_projection_adapter.dispatch_digest_projection",
    ]
    for fragment in moved_fragments:
        assert fragment not in source


def test_evidence_helper_preserves_link_types_and_store_calls():
    source = read_source(
        "backend/app/services/memory/writeback/meeting_memory_writeback/evidence_links.py"
    )
    for fragment in [
        '"reasoning_trace"',
        '"lens_receipt"',
        '"writeback_receipt"',
        '"task_execution"',
        '"artifact_result"',
        '"meeting_decision"',
        'link_role="supports"',
        'link_role="derived_from"',
        "evidence_link_store.exists",
        "evidence_link_store.create",
        "MemoryEvidenceLink.from_reasoning_trace",
        "MemoryEvidenceLink.from_lens_receipt",
        "MemoryEvidenceLink.from_writeback_receipt",
        "MemoryEvidenceLink.from_task_execution",
        "MemoryEvidenceLink.from_artifact_result",
        "MemoryEvidenceLink.from_meeting_decision",
    ]:
        assert fragment in source


def test_projection_helper_preserves_dispatch_contracts():
    source = read_source(
        "backend/app/services/memory/writeback/meeting_memory_writeback/projections.py"
    )
    for fragment in [
        "legacy_projection_adapter.dispatch_digest_projection",
        "metadata_projection_adapter.dispatch_digest_projection",
        "source_memory_item_id=source_memory_item_id",
        "source_writeback_run_id=source_writeback_run_id",
        "return True, None",
        "return False, str(exc)",
        "Legacy extraction dispatch failed",
        "Legacy metadata projection failed",
    ]:
        assert fragment in source


def test_collector_helper_preserves_phase2_registry_contracts():
    source = read_source(
        "backend/app/services/memory/writeback/meeting_memory_writeback/collectors.py"
    )
    for fragment in [
        "EvidenceCollectorRegistry",
        "StageResultEvidenceCollector",
        "ExecutionTraceEvidenceCollector",
        "IntentLogEvidenceCollector",
        "GovernanceDecisionEvidenceCollector",
        "LensPatchEvidenceCollector",
        "stage_result_collector",
        "execution_trace_collector",
        "intent_log_collector",
        "governance_decision_collector",
        "lens_patch_collector",
    ]:
        assert fragment in source


def test_touched_files_stay_under_large_file_gate_and_resource_rules():
    forbidden_resource_fragments = [
        "Queue(",
        "Thread(",
        "Process(",
        "create_engine(",
        "pgbouncer",
        "asyncio",
        "setInterval",
        "EventSource",
    ]
    for relative_path in TOUCHED_FILES:
        source = read_source(relative_path)
        line_count = source.count("\n")
        assert line_count <= 500, f"{relative_path} has {line_count} lines"
        assert not any("\u4e00" <= char <= "\u9fff" for char in source)
    for relative_path in PRODUCTION_FILES:
        source = read_source(relative_path)
        for fragment in forbidden_resource_fragments:
            assert fragment not in source
