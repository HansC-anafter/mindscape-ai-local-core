"""Unit tests for schema_path resolution guardrails."""

from pathlib import Path

import pytest

from backend.app.services.manifest_utils import resolve_tool_schema_paths


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolve_tool_schema_paths_loads_json_schema(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    _write(
        cap_dir / "tools" / "schemas" / "input.json",
        '{"type":"object","properties":{"name":{"type":"string"}}}',
    )
    manifest = {"tools": [{"name": "t", "schema_path": "tools/schemas/input.json"}]}
    resolve_tool_schema_paths(manifest, cap_dir)
    assert manifest["tools"][0]["input_schema"]["type"] == "object"


def test_resolve_tool_schema_paths_loads_yaml_schema(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    _write(
        cap_dir / "tools" / "schemas" / "input.yaml",
        "type: object\nproperties:\n  count:\n    type: integer\n",
    )
    manifest = {"tools": [{"name": "t", "schema_path": "tools/schemas/input.yaml"}]}
    resolve_tool_schema_paths(manifest, cap_dir)
    assert manifest["tools"][0]["input_schema"]["properties"]["count"]["type"] == "integer"


def test_resolve_tool_schema_paths_does_not_override_existing_input_schema(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    _write(cap_dir / "tools" / "schemas" / "input.json", '{"type":"object"}')
    manifest = {
        "tools": [
            {
                "name": "t",
                "schema_path": "tools/schemas/input.json",
                "input_schema": {"type": "string"},
            }
        ]
    }
    resolve_tool_schema_paths(manifest, cap_dir)
    assert manifest["tools"][0]["input_schema"] == {"type": "string"}


def test_resolve_tool_schema_paths_ignores_missing_schema_file(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    manifest = {"tools": [{"name": "t", "schema_path": "tools/schemas/missing.yaml"}]}
    resolve_tool_schema_paths(manifest, cap_dir)
    assert "input_schema" not in manifest["tools"][0]


def test_resolve_tool_schema_paths_rejects_parent_traversal(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    outside = tmp_path / "outside.yaml"
    _write(outside, "type: object\n")
    manifest = {
        "tools": [{"name": "t", "schema_path": "tools/schemas/../../../outside.yaml"}]
    }
    resolve_tool_schema_paths(manifest, cap_dir)
    assert "input_schema" not in manifest["tools"][0]


def test_resolve_tool_schema_paths_rejects_absolute_path(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    outside = tmp_path / "outside.yaml"
    _write(outside, "type: object\n")
    manifest = {"tools": [{"name": "t", "schema_path": str(outside.resolve())}]}
    resolve_tool_schema_paths(manifest, cap_dir)
    assert "input_schema" not in manifest["tools"][0]


def test_resolve_tool_schema_paths_rejects_symlink_escape(tmp_path: Path):
    cap_dir = tmp_path / "cap"
    outside = tmp_path / "outside.yaml"
    _write(outside, "type: object\n")

    link_path = cap_dir / "tools" / "schemas" / "link.yaml"
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink not supported in this environment")

    manifest = {"tools": [{"name": "t", "schema_path": "tools/schemas/link.yaml"}]}
    resolve_tool_schema_paths(manifest, cap_dir)
    assert "input_schema" not in manifest["tools"][0]
