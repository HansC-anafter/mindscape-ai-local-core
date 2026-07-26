import re
from pathlib import Path


def test_neutral_service_tree_has_no_artifact_or_caller_dispatch():
    repo_root = Path(__file__).resolve().parents[3]
    service_root = (
        repo_root / "backend/app/services/artifact_disclosure"
    )
    forbidden = re.compile(
        r"workspace_package_report|ReportBundleGraph|Meeting|agent|MCP|"
        r"pack_code|tenant|customer|\\.html|\\.zip",
        re.IGNORECASE,
    )
    violations = []
    for path in sorted(service_root.glob("*.py")):
        if forbidden.search(path.read_text(encoding="utf-8")):
            violations.append(path.name)

    assert violations == []


def test_report_adapter_cannot_own_policy_matrix_query_or_writer():
    repo_root = Path(__file__).resolve().parents[3]
    path = (
        repo_root
        / "backend/app/services/tools/reporting/"
        "report_disclosure_adapter.py"
    )
    content = path.read_text(encoding="utf-8")

    assert "LocalArtifactDisclosureService" not in content
    assert "write_report_bundle_archive" not in content
    assert "share.v1.json" not in content
    assert ".list_evidence(" not in content
