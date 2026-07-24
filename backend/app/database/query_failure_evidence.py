"""Public facade for redacted database failure evidence."""

from backend.app.database.query_failure_evidence_core import (
    QueryFailureEvidenceRecorder,
    attach_query_failure_evidence,
)

__all__ = ["QueryFailureEvidenceRecorder", "attach_query_failure_evidence"]
