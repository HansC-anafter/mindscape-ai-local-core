from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_security_middleware_admits_before_lazy_activation() -> None:
    source = (
        ROOT / "backend/app/app_bootstrap/error_handlers.py"
    ).read_text(encoding="utf-8")
    admission = source.index(
        "await admit_workspace_capability_request(request)"
    )
    activation = source.index(
        "await ensure_capability_activation_for_request(request)"
    )
    assert admission < activation


def test_admission_modules_have_one_crs_caller_and_no_site_hub_client() -> None:
    directory = (
        ROOT
        / "backend/app/services/workspace_capability_admission"
    )
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in directory.glob("*.py")
    }
    callers = [
        name
        for name, source in sources.items()
        if "/api/v1/crs/external-executions/authorize" in source
    ]
    assert callers == ["external_execution_adapter.py"]
    assert all(
        "site_hub" not in source.lower()
        and "site-hub" not in source.lower()
        for source in sources.values()
    )


def test_request_admission_is_bounded_and_does_not_poll() -> None:
    source = (
        ROOT
        / "backend/app/app_bootstrap/workspace_capability_request_admission.py"
    ).read_text(encoding="utf-8")
    assert "setInterval" not in source
    assert "while True" not in source
    assert "64 * 1024" in source
    assert len(source.splitlines()) < 240

