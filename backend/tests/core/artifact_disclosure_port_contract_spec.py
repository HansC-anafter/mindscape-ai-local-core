from __future__ import annotations

import re
from pathlib import Path


def test_neutral_host_has_no_report_or_caller_literals():
    repo_root = Path(__file__).resolve().parents[3]
    paths = [
        repo_root / "backend/app/core/ports/artifact_disclosure.py",
        *sorted(
            (
                repo_root / "backend/app/services/artifact_disclosure"
            ).glob("*.py")
        ),
    ]
    forbidden = re.compile(
        r"workspace_package_report|ReportBundleGraph|Meeting|agent|MCP|"
        r"pack_code|tenant|customer|\.html|\.zip",
        re.IGNORECASE,
    )
    violations = {
        str(path.relative_to(repo_root)): sorted(
            set(forbidden.findall(path.read_text(encoding="utf-8")))
        )
        for path in paths
        if forbidden.search(path.read_text(encoding="utf-8"))
    }
    assert violations == {}


def test_report_adapter_has_no_policy_or_writer_implementation():
    repo_root = Path(__file__).resolve().parents[3]
    path = (
        repo_root
        / "backend/app/services/tools/reporting/report_disclosure_adapter.py"
    )
    content = path.read_text(encoding="utf-8")
    forbidden = (
        "LocalArtifactDisclosureService",
        "write_report_bundle_archive",
        "share.v1.json",
    )
    assert [token for token in forbidden if token in content] == []
