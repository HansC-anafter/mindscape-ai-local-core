"""Report adapter composition without a report-local policy fallback."""

from functools import lru_cache

from backend.app.services.artifact_disclosure import (
    build_artifact_disclosure_port,
)
from backend.app.services.tools.reporting.report_disclosure_adapter import (
    WorkspaceReportDisclosureAdapter,
)


@lru_cache(maxsize=1)
def build_workspace_report_disclosure_adapter(
) -> WorkspaceReportDisclosureAdapter:
    return WorkspaceReportDisclosureAdapter(
        disclosure_port=build_artifact_disclosure_port(),
    )


__all__ = ["build_workspace_report_disclosure_adapter"]
