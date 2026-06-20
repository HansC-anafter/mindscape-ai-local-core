import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / "scripts" / "e2e"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
TARGET_FILES = [
    SCRIPT_DIR / "pd_ux_aol_acceptance.py",
    SCRIPT_DIR / "pd_ux_aol_acceptance_common.py",
    SCRIPT_DIR / "pd_ux_aol_acceptance_runtime.py",
    SCRIPT_DIR / "pd_ux_aol_acceptance_compilers.py",
    SCRIPT_DIR / "pd_ux_aol_acceptance_browser.py",
    SCRIPT_DIR / "pd_ux_aol_acceptance_runner.py",
]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in TARGET_FILES}


def test_facade_imports_runner_and_keeps_cli_defaults(monkeypatch):
    for key in [
        "PD_UX_E2E_FRONTEND_URL",
        "PD_UX_E2E_API_URL",
        "PD_UX_E2E_CONTROL_URL",
        "PD_UX_E2E_OWNER_USER_ID",
        "PD_UX_E2E_WORKSPACE_ID",
        "PD_UX_E2E_SESSION_ID",
        "PD_UX_E2E_SCENE_ID",
        "PD_UX_E2E_ARTIFACT_ID",
        "PD_UX_E2E_OUTPUT_DIR",
        "PD_UX_E2E_TIMEOUT_MS",
        "PD_UX_E2E_CODEX_QUOTA_MAX_RUNTIME_PROBES",
        "PD_UX_E2E_CODEX_QUOTA_TIMEOUT_SECONDS",
        "PD_UX_E2E_CODEX_QUOTA_STALL_TIMEOUT_SECONDS",
    ]:
        monkeypatch.delenv(key, raising=False)

    module = _load_module("pd_ux_aol_acceptance_under_test", TARGET_FILES[0])
    args = module.parse_args([])

    assert callable(module.run_acceptance)
    assert callable(module.main)
    assert args.frontend_url == "http://127.0.0.1:8300"
    assert args.api_url == "http://127.0.0.1:8200"
    assert args.control_url == "http://127.0.0.1:8220"
    assert args.owner_user_id == "default-user"
    assert args.output_dir == ".tmp/e2e/pd-ux-aol"
    assert args.timeout_ms == 45000
    assert args.skip_codex_quota_preflight is False
    assert args.continue_on_codex_quota_failure is False
    assert args.codex_quota_max_runtime_probes == 8
    assert args.codex_quota_timeout_seconds == 90
    assert args.codex_quota_stall_timeout_seconds == 30
    assert args.headed is False


def test_common_helpers_finalize_and_write_acceptance_result(tmp_path):
    module = _load_module("pd_ux_aol_acceptance_common_under_test", TARGET_FILES[1])
    stages = {stage_id: module._stage_template(stage_id) for stage_id in module.STAGES}
    for stage_id in module.STAGES:
        module._add_check(stages, stage_id, "source-only seam check", True)

    result = module._write_acceptance_result(
        started=0.0,
        output_dir=tmp_path,
        stages=stages,
        workspace_id="workspace-a",
        session_id="session-a",
        scene_id="scene-a",
        artifact_id="artifact-a",
        project_id="project-a",
        object_ref={"uri": "mindscape://object-a"},
    )

    result_path = tmp_path / "pd-ux-aol-acceptance-result.json"
    assert result["status"] == "passed"
    assert result["failed_stages"] == []
    assert result["result_json"] == str(result_path)
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "passed"


def test_runtime_route_evidence_uses_bound_available_runtime_ids():
    module = _load_module("pd_ux_aol_acceptance_runtime_under_test", TARGET_FILES[2])
    evidence = module._runtime_route_evidence(
        {
            "route_policy": {
                "primary_executor_runtime": "runtime-a",
                "resolved_executor_runtime": "runtime-b",
                "dispatch_chain": ["runtime-c"],
                "surfaces": {
                    "runtime-d": {"enabled": True},
                    "surface-x": {"enabled": True, "preferred_runtime_id": "runtime-e"},
                },
            },
            "agents": {
                "agents": [
                    {"id": "runtime-a", "status": "available", "transport": "host"},
                    {"id": "runtime-b", "status": "offline", "reason": "test"},
                    {"id": "runtime-e", "status": "available"},
                ]
            },
        }
    )

    assert evidence["bound_runtime_ids"] == [
        "runtime-a",
        "runtime-b",
        "runtime-d",
        "surface-x",
        "runtime-e",
        "runtime-c",
    ]
    assert evidence["available_bound_runtime_ids"] == ["runtime-a", "runtime-e"]


def test_source_boundaries_keep_resource_paths_single_owner():
    sources = _sources()
    combined = "\n".join(sources.values())

    assert combined.count("def main(") == 1
    assert combined.count("def run_acceptance(") == 1
    assert all(source.count("\n") + 1 < 500 for source in sources.values())
    assert "sync_playwright" in sources["pd_ux_aol_acceptance_browser.py"]
    assert all(
        "sync_playwright" not in source
        for name, source in sources.items()
        if name != "pd_ux_aol_acceptance_browser.py"
    )
    assert sources["pd_ux_aol_acceptance_common.py"].count("urllib.request.urlopen") == 1
    assert all(
        "urllib.request.urlopen" not in source
        for name, source in sources.items()
        if name != "pd_ux_aol_acceptance_common.py"
    )
    assert sources["pd_ux_aol_acceptance_runtime.py"].count("time.sleep(") == 2
    assert all(
        "time.sleep(" not in source
        for name, source in sources.items()
        if name != "pd_ux_aol_acceptance_runtime.py"
    )
    assert sources["pd_ux_aol_acceptance_runtime.py"].count("asyncio.run(") == 1
    assert all(
        "asyncio.run(" not in source
        for name, source in sources.items()
        if name != "pd_ux_aol_acceptance_runtime.py"
    )
    assert sources["pd_ux_aol_acceptance_common.py"].count(
        "pd-ux-aol-acceptance-result.json"
    ) == 1
    assert sources["pd_ux_aol_acceptance_browser.py"].count(
        "pd-ux-aol-acceptance.png"
    ) == 1

    for token in [
        "subprocess",
        "APIRouter",
        "@router",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "Thread(",
        "Process(",
        "setInterval",
    ]:
        assert token not in combined
