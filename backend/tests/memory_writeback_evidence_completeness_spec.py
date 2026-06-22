from backend.app.services.memory.writeback.evidence_completeness import (
    summarize_writeback_evidence_completeness,
)


def test_writeback_evidence_completeness_marks_verified_with_supporting_evidence():
    summary = summarize_writeback_evidence_completeness(
        {
            "digest": object(),
            "item": object(),
            "meeting_decision_count": 1,
            "task_execution_count": 1,
        }
    )

    assert summary["status"] == "verified"
    assert summary["missing_required"] == []
    assert summary["supporting_evidence"] == ["meeting_decision", "task_execution"]


def test_writeback_evidence_completeness_marks_candidate_when_required_source_missing():
    summary = summarize_writeback_evidence_completeness(
        {
            "digest": object(),
            "item": None,
            "meeting_decision_count": 1,
        }
    )

    assert summary["status"] == "candidate"
    assert summary["missing_required"] == ["memory_item"]
