import subprocess
from pathlib import Path

from backend.app.services.post_install.playbook_validator import PlaybookValidator
from backend.app.services.runtime_contract_paths import (
    build_validation_pythonpath,
    resolve_capability_import_roots,
    resolve_runtime_contracts_root,
)


def test_playbook_validator_uses_contract_aware_pythonpath(
    tmp_path: Path,
    monkeypatch,
):
    local_core_root = tmp_path / "mindscape-ai-local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    validate_script = local_core_root / "scripts" / "validate_playbooks.py"
    validate_script.parent.mkdir(parents=True)
    validate_script.write_text("", encoding="utf-8")
    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '{"validations":[{"playbook_code":"demo_playbook",'
                '"passed":true,"results":[]}]}'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    validator = PlaybookValidator(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    validation_results = {"validated": [], "failed": [], "skipped": []}

    assert validator._validate_structure(
        "demo_playbook",
        "demo_pack",
        validate_script,
        validation_results,
    )
    assert captured["env"]["PYTHONPATH"] == build_validation_pythonpath(
        local_core_root,
        capabilities_dir,
    )
    pythonpath_parts = captured["env"]["PYTHONPATH"].split(":")
    runtime_root = str(resolve_runtime_contracts_root(local_core_root))
    backend_root = str(resolve_capability_import_roots(capabilities_dir)[0])

    assert runtime_root in pythonpath_parts
    assert backend_root in pythonpath_parts
    assert pythonpath_parts.index(runtime_root) < pythonpath_parts.index(backend_root)
