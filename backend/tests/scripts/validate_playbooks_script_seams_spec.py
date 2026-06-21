import importlib.util
import json
from pathlib import Path

from scripts.validate_playbooks_lib import cli, execution, settings
from scripts.validate_playbooks_lib.validator import PlaybookValidator


REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_playbook_spec(root: Path, capability: str, playbook_code: str) -> Path:
    specs_dir = root / capability / "playbooks" / "specs"
    specs_dir.mkdir(parents=True)
    spec_path = specs_dir / f"{playbook_code}.json"
    spec_path.write_text(
        json.dumps(
            {
                "playbook_code": playbook_code,
                "steps": [
                    {
                        "id": "extract",
                        "tool_slot": "core_llm.structured_extract",
                        "outputs": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return spec_path


def test_validator_discovers_and_validates_temp_playbook(
    tmp_path: Path, monkeypatch
) -> None:
    capabilities_root = tmp_path / "capabilities"
    _write_playbook_spec(capabilities_root, "demo_pack", "demo_playbook")
    monkeypatch.setattr(settings, "CAPABILITIES_PATH", capabilities_root)

    validator = PlaybookValidator()
    validator._skip_execution = True

    playbooks = validator.discover_playbooks(capability="demo_pack")
    assert [(capability, code) for capability, code, _ in playbooks] == [
        ("demo_pack", "demo_playbook")
    ]

    validation = validator.validate_playbook(*playbooks[0])
    assert validation.capability == "demo_pack"
    assert validation.playbook_code == "demo_playbook"
    assert validation.passed
    assert [result.check_name for result in validation.results] == [
        "spec_json_valid",
        "spec_has_playbook_code",
        "spec_has_steps",
        "spec_has_steps",
        "tool_exists_core_llm.structured_extract",
    ]


def test_cli_json_output_uses_existing_summary_shape(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    capabilities_root = tmp_path / "capabilities"
    _write_playbook_spec(capabilities_root, "demo_pack", "demo_playbook")
    monkeypatch.setattr(settings, "CAPABILITIES_PATH", capabilities_root)

    exit_code = cli.main(["--capability", "demo_pack", "--json", "--skip-execution"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert payload["validations"][0]["capability"] == "demo_pack"
    assert payload["validations"][0]["playbook_code"] == "demo_playbook"
    assert payload["validations"][0]["passed"] is True


def test_script_facade_exports_public_validation_contract() -> None:
    script_path = REPO_ROOT / "scripts" / "validate_playbooks.py"
    spec = importlib.util.spec_from_file_location(
        "validate_playbooks_facade", script_path
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PlaybookValidator.__name__ == PlaybookValidator.__name__
    assert module.PlaybookValidator.__module__.endswith(
        "validate_playbooks_lib.validator"
    )
    assert module.main.__name__ == cli.main.__name__
    assert module.main.__module__.endswith("validate_playbooks_lib.cli")
    assert module.ValidationResult.__name__ == "ValidationResult"
    assert module.PlaybookValidation.__name__ == "PlaybookValidation"


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _ApiFailureSession:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url: str, **kwargs):
        self.calls.append(("get", url))
        if url.endswith("/api/v1/workspaces"):
            return _FakeResponse(
                200,
                [{"id": "workspace-1", "title": "Validate: demo_playbook"}],
            )
        raise AssertionError("Cleanup should not run after execution API failure")

    def post(self, url: str, **kwargs):
        self.calls.append(("post", url))
        return _FakeResponse(500, text="execution failed")


def test_execution_api_failure_preserves_no_cleanup_return_path(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_MOCK", True)
    session = _ApiFailureSession()

    results = execution.validate_execution(
        session=session,
        timeout=30,
        base_url="http://runtime.test",
        playbook_code="demo_playbook",
        capability="demo_pack",
    )

    assert [call[0] for call in session.calls] == ["get", "post"]
    assert results[-1].check_name == "execution_api_call"
    assert results[-1].passed is False
