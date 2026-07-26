from backend.app.services.artifact_disclosure.composition import (
    build_artifact_disclosure_port,
)
from backend.app.services.artifact_disclosure.service import (
    LocalArtifactDisclosureService,
)
from backend.app.services.tools.reporting.report_disclosure_composition import (
    build_workspace_report_disclosure_adapter,
)


def test_production_composition_binds_one_cached_port_instance():
    build_artifact_disclosure_port.cache_clear()
    build_workspace_report_disclosure_adapter.cache_clear()

    first = build_artifact_disclosure_port()
    second = build_artifact_disclosure_port()
    adapter = build_workspace_report_disclosure_adapter()

    assert first is second
    assert isinstance(first, LocalArtifactDisclosureService)
    assert adapter._port is first
