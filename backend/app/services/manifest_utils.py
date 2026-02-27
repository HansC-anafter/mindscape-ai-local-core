"""
Manifest Utilities

Shared helpers for loading and post-processing capability manifest.yaml files.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None


def resolve_tool_schema_paths(
    manifest: Dict[str, Any],
    cap_dir: Path,
) -> Dict[str, Any]:
    """
    Resolve ``schema_path`` references in tool definitions to inline
    ``input_schema``.

    For each tool that declares ``schema_path`` but *not* ``input_schema``,
    the referenced file is loaded and injected as ``input_schema``.

    Args:
        manifest: Parsed manifest dict (mutated in-place).
        cap_dir:  Root directory of the capability pack
                  (the folder containing manifest.yaml).

    Returns:
        The same *manifest* dict (for convenience chaining).
    """
    cap_root = cap_dir.resolve()

    for tool in manifest.get("tools", []) or []:
        if not isinstance(tool, dict):
            continue

        schema_path_str = tool.get("schema_path")
        if not schema_path_str or "input_schema" in tool:
            continue

        schema_path = Path(schema_path_str)
        if schema_path.is_absolute():
            tool_name = tool.get("name") or tool.get("code") or "unknown"
            logger.warning(
                "schema_path for tool '%s' must be relative, got absolute path: %s",
                tool_name,
                schema_path_str,
            )
            continue

        schema_file = (cap_root / schema_path).resolve()
        # Guard: reject paths that escape the capability pack directory
        try:
            schema_file.relative_to(cap_root)
        except ValueError:
            tool_name = tool.get("name") or tool.get("code") or "unknown"
            logger.warning(
                "schema_path for tool '%s' escapes pack directory (path traversal): %s",
                tool_name,
                schema_path_str,
            )
            continue
        if not schema_file.exists():
            tool_name = tool.get("name") or tool.get("code") or "unknown"
            logger.warning(
                "schema_path file not found for tool '%s': %s",
                tool_name,
                schema_file,
            )
            continue

        try:
            with schema_file.open("r", encoding="utf-8") as f:
                if schema_file.suffix == ".json":
                    tool["input_schema"] = json.load(f)
                elif yaml is not None:
                    tool["input_schema"] = yaml.safe_load(f)
                else:
                    logger.warning(
                        "Cannot load YAML schema (PyYAML not installed): %s",
                        schema_file,
                    )
        except Exception as exc:
            tool_name = tool.get("name") or tool.get("code") or "unknown"
            logger.warning(
                "Failed to load schema_path for tool '%s' from %s: %s",
                tool_name,
                schema_file,
                exc,
            )

    return manifest
