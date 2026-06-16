import subprocess
from pathlib import Path

from backend.app.services.post_install_modules import playbook_structure_validation
from backend.app.services.post_install_modules.playbook_validator import PlaybookValidator
from backend.app.services.runtime_contract_paths import build_validation_pythonpath


def test_post_install_modules_playbook_validator_exports_structure_mixin() -> None:
    assert PlaybookValidator._validate_capability_structure.__module__.endswith(
        "playbook_structure_validation"
    )
    assert PlaybookValidator._extract_json_output.__module__.endswith(
        "playbook_structure_validation"
    )


def test_batched_structure_validation_uses_fake_subprocess_and_contract_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_core_root = tmp_path / "mindscape-ai-local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    validate_script = local_core_root / "scripts" / "validate_playbooks.py"
    validate_script.parent.mkdir(parents=True)
    validate_script.write_text("", encoding="utf-8")
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '{"validations":[{"playbook_code":"demo_playbook",'
                '"passed":true,"results":[]}]}'
            ),
            stderr="",
        )

    monkeypatch.setattr(playbook_structure_validation.subprocess, "run", fake_run)

    validator = PlaybookValidator(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    validation_results = {"validated": [], "failed": [], "skipped": []}

    result = validator._validate_capability_structure(
        "demo_pack",
        {"demo_playbook"},
        validate_script,
        validation_results,
    )

    assert result == {"demo_playbook": True}
    assert validation_results == {"validated": [], "failed": [], "skipped": []}
    assert captured["args"][1:] == [
        str(validate_script),
        "--capability",
        "demo_pack",
        "--json",
        "--skip-execution",
    ]
    assert captured["kwargs"]["cwd"] == str(local_core_root)
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["timeout"] == 30
    assert captured["kwargs"]["env"]["PYTHONPATH"] == build_validation_pythonpath(
        local_core_root,
        capabilities_dir,
    )
    assert captured["kwargs"]["env"]["CAPABILITIES_PATH"] == str(capabilities_dir)
