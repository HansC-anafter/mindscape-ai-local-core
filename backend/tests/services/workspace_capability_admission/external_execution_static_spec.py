from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENDPOINT = "/api/v1/crs/external-executions/authorize"


def test_new_crs_endpoint_has_one_local_core_caller():
    matches = []
    for path in (ROOT / "app").rglob("*.py"):
        if ENDPOINT in path.read_text(encoding="utf-8"):
            matches.append(path.relative_to(ROOT).as_posix())
    assert matches == [
        (
            "app/services/workspace_capability_admission/"
            "external_execution_adapter.py"
        )
    ]


def test_adapter_has_no_site_hub_or_local_fallback():
    source = (
        ROOT
        / "app/services/workspace_capability_admission/"
        "external_execution_adapter.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()
    assert "site_hub" not in lowered
    assert "site-hub" not in lowered
    assert "fallback" not in lowered
