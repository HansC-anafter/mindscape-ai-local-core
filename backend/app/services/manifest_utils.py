"""
Manifest Utilities

Shared helpers for loading and post-processing capability manifest.yaml files.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

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


# ---------------------------------------------------------------------------
# Playbook asset declaration resolver
# ---------------------------------------------------------------------------

_PRODUCES_CACHE: Dict[str, Any] = {}  # playbook_code -> [{"type": ..., "label": ...}]
_CACHE_BUILT = False


def _build_produces_cache(capabilities_dir: Optional[Path] = None) -> None:
    """Scan all installed manifests and cache playbook produces declarations."""
    global _CACHE_BUILT
    if _CACHE_BUILT:
        return

    if capabilities_dir is None:
        # Default: inside Docker container
        candidates = [
            Path("/app/backend/app/capabilities"),
            Path(__file__).resolve().parent.parent / "capabilities",
        ]
        for c in candidates:
            if c.is_dir():
                capabilities_dir = c
                break
    if not capabilities_dir or not capabilities_dir.is_dir():
        _CACHE_BUILT = True
        return

    for cap_dir in capabilities_dir.iterdir():
        if not cap_dir.is_dir() or cap_dir.name.startswith(("_", ".")):
            continue
        manifest_path = cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            if yaml is None:
                continue
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}
            for pb in manifest.get("playbooks", []) or []:
                if not isinstance(pb, dict):
                    continue
                code = pb.get("code")
                produces = pb.get("produces")
                if code and produces:
                    _PRODUCES_CACHE[code] = produces
        except Exception as exc:
            logger.debug("Failed to parse manifest %s: %s", manifest_path, exc)

    _CACHE_BUILT = True
    logger.info(
        "Produces cache built: %d playbooks with declarations", len(_PRODUCES_CACHE)
    )


def resolve_playbook_produces(playbook_code: str) -> list:
    """Return the produces declarations for a playbook code.

    Returns a list of dicts: [{"type": "...", "label": "...", "storage": "..."}]
    Returns empty list if no produces declared.
    """
    _build_produces_cache()
    return _PRODUCES_CACHE.get(playbook_code, [])
