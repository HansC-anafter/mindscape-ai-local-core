import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import yaml

from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir
from backend.app.models.tool_registry import RegisteredTool
from .tool_policy import _registered_tool_from_manifest_tool

logger = logging.getLogger(__name__)

ManifestFingerprint = Tuple[Tuple[str, int, int, int, int], ...]


def _installed_manifest_fingerprint(capabilities_dir: Path) -> ManifestFingerprint:
    """Describe the installed manifest set without parsing manifest contents."""
    manifests = []
    for cap_dir in capabilities_dir.iterdir():
        if not cap_dir.is_dir() or is_ignored_runtime_pack_dir(cap_dir.name):
            continue
        manifest_path = cap_dir / "manifest.yaml"
        try:
            stat = manifest_path.stat()
        except FileNotFoundError:
            continue
        manifests.append(
            (
                str(manifest_path),
                stat.st_dev,
                stat.st_ino,
                stat.st_mtime_ns,
                stat.st_size,
            )
        )
    return tuple(sorted(manifests))


@lru_cache(maxsize=8)
def _load_manifest_tools_for_fingerprint(
    fingerprint: ManifestFingerprint,
) -> Tuple[RegisteredTool, ...]:
    """Parse one immutable manifest-set fingerprint."""
    results: List[RegisteredTool] = []
    for manifest_path_value, _device, _inode, _mtime_ns, _size in fingerprint:
        manifest_path = Path(manifest_path_value)
        cap_dir = manifest_path.parent
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.debug(f"Failed to read manifest for {cap_dir.name}: {e}")
            continue

        cap_code = manifest.get("code") or cap_dir.name
        for tool_cfg in manifest.get("tools", []) or []:
            if not isinstance(tool_cfg, dict):
                continue
            tool_code = tool_cfg.get("code") or tool_cfg.get("name")
            if not tool_code:
                continue
            registered_tool = _registered_tool_from_manifest_tool(
                capability_code=cap_code,
                tool_cfg=tool_cfg,
            )
            if registered_tool is not None:
                results.append(registered_tool)
    return tuple(results)


def _load_capability_tools_from_installed_manifests() -> List[RegisteredTool]:
    """
    Fallback: load capability tools from installed capability manifests.

    Why this exists:
    - `ToolListService._get_capability_tools()` relies on capability registry state.
    - During hot-reload / startup ordering issues, registry-based enumeration can be empty.
    - Installed manifests in `backend/app/capabilities/*/manifest.yaml` are the install SOT.
    """
    try:
        # Resolve `backend/app` directory from this file: backend/app/routes/core/tools/manifest_tools.py
        app_dir = Path(__file__).resolve().parents[3]  # .../backend/app
        capabilities_dir = app_dir / "capabilities"
        if not capabilities_dir.exists():
            return []

        fingerprint = _installed_manifest_fingerprint(capabilities_dir)
        return list(_load_manifest_tools_for_fingerprint(fingerprint))
    except Exception as e:
        logger.warning(f"Fallback capability tool load failed: {e}", exc_info=True)
        return []
