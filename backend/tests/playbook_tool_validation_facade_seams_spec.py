import json
import sys
import types
from pathlib import Path

import yaml

from backend.app.services.playbook_installer_core import tool_validation


def _install_fake_tool_executor(monkeypatch):
    fake_module = types.ModuleType("backend.app.shared.tool_executor")

    class ToolExecutor:
        pass

    fake_module.ToolExecutor = ToolExecutor
    monkeypatch.setitem(sys.modules, "backend.app.shared.tool_executor", fake_module)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_tool_validation_facade_reexports_planned_helper_names():
    for name in [
        "validate_tools_direct_call",
        "_load_optional_python_packages",
        "_load_required_capabilities",
        "_get_backend_from_manifest",
        "_discover_capability_dir",
        "_ensure_capabilities_package",
        "_preload_models",
        "_ensure_tool_capability_package",
        "_preload_tool_models",
        "_ensure_importable_tool_parent",
        "_is_optional_import_error",
    ]:
        assert callable(getattr(tool_validation, name))


def test_validate_tools_direct_call_downgrades_optional_import_error(
    monkeypatch, tmp_path
):
    _install_fake_tool_executor(monkeypatch)
    capabilities_dir = tmp_path / "backend" / "app" / "capabilities"
    specs_dir = tmp_path / "backend" / "playbooks" / "specs"

    _write_yaml(
        capabilities_dir / "demo_pack_optional" / "manifest.yaml",
        {
            "dependencies": {
                "python_packages": {"optional": ["missing_optional_pkg"]}
            }
        },
    )
    _write_yaml(
        capabilities_dir / "demo_tools_optional" / "manifest.yaml",
        {
            "tools": [
                {
                    "code": "do_thing",
                    "backend": "app.capabilities.demo_tools_optional.tool_impl:run",
                }
            ]
        },
    )
    tool_file = capabilities_dir / "demo_tools_optional" / "tool_impl.py"
    tool_file.write_text("import missing_optional_pkg\n\ndef run():\n    return None\n")

    _write_json(
        specs_dir / "demo_playbook_optional.json",
        {
            "required_capabilities": ["demo_tools_optional"],
            "steps": [
                {
                    "id": "optional_import",
                    "tool_slot": "demo_tools_optional.do_thing",
                }
            ],
        },
    )

    errors, warnings = tool_validation.validate_tools_direct_call(
        playbook_code="demo_playbook_optional",
        capability_code="demo_pack_optional",
        capabilities_dir=capabilities_dir,
        specs_dir=specs_dir,
        tool_model_preload_cache={},
    )

    assert errors == []
    assert len(warnings) == 1
    assert "optional dependency issue" in warnings[0]
    assert "missing_optional_pkg" in warnings[0]


def test_validate_tools_direct_call_reports_required_backend_missing(
    monkeypatch, tmp_path
):
    _install_fake_tool_executor(monkeypatch)
    capabilities_dir = tmp_path / "backend" / "app" / "capabilities"
    specs_dir = tmp_path / "backend" / "playbooks" / "specs"

    _write_yaml(capabilities_dir / "demo_pack_required" / "manifest.yaml", {})
    _write_json(
        specs_dir / "demo_playbook_required.json",
        {
            "required_capabilities": ["missing_tools_required"],
            "steps": [
                {
                    "id": "required_missing",
                    "tool_slot": "missing_tools_required.do_thing",
                }
            ],
        },
    )

    import backend.app.services.capability_registry as capability_registry

    monkeypatch.setattr(
        capability_registry,
        "get_tool_backend",
        lambda capability_name, tool_name: None,
    )

    errors, warnings = tool_validation.validate_tools_direct_call(
        playbook_code="demo_playbook_required",
        capability_code="demo_pack_required",
        capabilities_dir=capabilities_dir,
        specs_dir=specs_dir,
    )

    assert errors == [
        "Step 'required_missing': Tool 'missing_tools_required.do_thing' backend not found (required capability)"
    ]
    assert warnings == []
