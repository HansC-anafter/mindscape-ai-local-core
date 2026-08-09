import json
import sys
import types
from pathlib import Path

import yaml

from backend.app.services.pack_validation_background_core import (
    validate_installed_playbooks_isolated,
)


def test_background_validation_ignores_stale_runtime_module_cache(
    monkeypatch,
    tmp_path,
):
    repository_root = Path(__file__).resolve().parents[2]
    capabilities_dir = tmp_path / "backend" / "app" / "capabilities"
    specs_dir = tmp_path / "backend" / "playbooks" / "specs"
    capability_dir = capabilities_dir / "demo_pack"
    services_dir = capability_dir / "services"
    scripts_dir = tmp_path / "scripts"

    services_dir.mkdir(parents=True)
    specs_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "validate_playbooks.py").write_text(
        """
import json

print(json.dumps({
    "validations": [{
        "playbook_code": "demo_playbook",
        "passed": True,
        "results": [],
    }]
}))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (capability_dir / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "tools": [
                    {
                        "code": "fresh_tool",
                        "backend": "capabilities.demo_pack.services.target:run",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (services_dir / "target.py").write_text(
        "def run():\n    return 'fresh'\n",
        encoding="utf-8",
    )
    (specs_dir / "demo_playbook.json").write_text(
        json.dumps(
            {
                "required_capabilities": ["demo_pack"],
                "steps": [
                    {
                        "id": "fresh_import",
                        "tool_slot": "demo_pack.fresh_tool",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    stale_module_name = "capabilities.demo_pack.services.target"
    stale_module = types.ModuleType(stale_module_name)
    monkeypatch.setitem(sys.modules, stale_module_name, stale_module)
    monkeypatch.setenv(
        "PYTHONPATH",
        str(repository_root),
    )

    result = validate_installed_playbooks_isolated(
        pack_id="demo_pack",
        manifest={"playbooks": [{"code": "demo_playbook"}]},
        local_core_root=tmp_path,
        capabilities_dir=capabilities_dir,
        specs_dir=specs_dir,
    )

    assert result.errors == [], result.to_dict()
    assert result.playbook_validation["validated"] == ["demo_playbook"]
    assert sys.modules[stale_module_name] is stale_module
