"""
Capability Packs API compatibility entrypoint.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .capability_packs_core import installed_routes as _installed_routes
from .capability_packs_core import manifest_scan as _manifest_scan
from .capability_packs_core.activation_routes import (
    disable_pack,
    enable_pack,
    get_pack_activation_state,
    list_enabled_packs,
    list_installed_packs,
    list_packs,
)
from .capability_packs_core.router import router
from .capability_packs_core.schemas import (
    PackActivationStateResponse,
    PackResponse,
)

_core_format_ui_component_for_response = (
    _installed_routes._format_ui_component_for_response
)
_pack_yaml_cache = _manifest_scan._pack_yaml_cache
_pack_yaml_cache_time = _manifest_scan._pack_yaml_cache_time
_pack_yaml_cache_lock = _manifest_scan._pack_yaml_cache_lock
_PACK_YAML_CACHE_TTL_SECONDS = _manifest_scan._PACK_YAML_CACHE_TTL_SECONDS
_PACK_SOURCE_PRIORITY = _manifest_scan._PACK_SOURCE_PRIORITY
_WORKSPACE_TOOL_ID_PATTERN = _manifest_scan._WORKSPACE_TOOL_ID_PATTERN


def _sync_manifest_to_core() -> None:
    _manifest_scan._pack_yaml_cache = _pack_yaml_cache
    _manifest_scan._pack_yaml_cache_time = _pack_yaml_cache_time
    _manifest_scan._pack_yaml_cache_lock = _pack_yaml_cache_lock
    _manifest_scan._scan_pack_yaml_files_uncached = _scan_pack_yaml_files_uncached


def _sync_manifest_from_core() -> None:
    global _pack_yaml_cache, _pack_yaml_cache_time
    _pack_yaml_cache = _manifest_scan._pack_yaml_cache
    _pack_yaml_cache_time = _manifest_scan._pack_yaml_cache_time


def _sync_installed_route_helpers() -> None:
    _installed_routes._scan_pack_yaml_files = _scan_pack_yaml_files
    _installed_routes._get_pack_meta_by_code = _get_pack_meta_by_code
    _installed_routes._get_installed_pack_ids = _get_installed_pack_ids
    _installed_routes._format_installed_capability = _format_installed_capability
    _installed_routes._format_ui_component_for_response = (
        _core_format_ui_component_for_response
    )
    _installed_routes._WORKSPACE_TOOL_ID_PATTERN = _WORKSPACE_TOOL_ID_PATTERN


def _utc_now():
    return _manifest_scan._utc_now()


def _load_manifest_file(manifest_path: Path) -> Optional[Dict[str, Any]]:
    return _manifest_scan._load_manifest_file(manifest_path)


def _safe_pack_code_variants(capability_code: str) -> List[str]:
    return _manifest_scan._safe_pack_code_variants(capability_code)


def _pack_root_candidates(base_dir: Path, child_path: str):
    return _manifest_scan._pack_root_candidates(base_dir, child_path)


def _candidate_pack_manifest_paths(
    capability_code: str,
    base_dir: Optional[Path] = None,
):
    return _manifest_scan._candidate_pack_manifest_paths(capability_code, base_dir)


def _map_pack_manifest_for_source(pack_meta, source_kind, default_id, manifest_path):
    return _manifest_scan._map_pack_manifest_for_source(
        pack_meta,
        source_kind,
        default_id,
        manifest_path,
    )


def _get_pack_meta_by_code(capability_code: str, base_dir: Optional[Path] = None):
    _sync_manifest_to_core()
    result = _manifest_scan._get_pack_meta_by_code(capability_code, base_dir)
    _sync_manifest_from_core()
    return result


def _format_installed_capability(pack_meta: Dict[str, Any]) -> Dict[str, Any]:
    return _manifest_scan._format_installed_capability(pack_meta)


def _normalize_enabled_by_default(value: Any) -> bool:
    return _manifest_scan._normalize_enabled_by_default(value)


def _merge_unique_items(left: Any, right: Any) -> List[Any]:
    return _manifest_scan._merge_unique_items(left, right)


def _merge_pack_meta(existing: Dict[str, Any], candidate: Dict[str, Any]):
    return _manifest_scan._merge_pack_meta(existing, candidate)


def _map_runtime_manifest(manifest_path: Path):
    return _manifest_scan._map_runtime_manifest(manifest_path)


def _is_pack_yaml_cache_fresh(now: Optional[float] = None) -> bool:
    _sync_manifest_to_core()
    result = _manifest_scan._is_pack_yaml_cache_fresh(now)
    _sync_manifest_from_core()
    return result


def _scan_pack_yaml_files_uncached(base_dir: Optional[Path] = None):
    return _manifest_scan._scan_pack_yaml_files_uncached(base_dir)


def _scan_pack_yaml_files(base_dir: Optional[Path] = None):
    _sync_manifest_to_core()
    result = _manifest_scan._scan_pack_yaml_files(base_dir)
    _sync_manifest_from_core()
    return result


def _get_installed_pack_ids() -> set:
    return _manifest_scan._get_installed_pack_ids()


def _get_enabled_pack_ids() -> set:
    return _manifest_scan._get_enabled_pack_ids()


def list_installed_capabilities():
    _sync_installed_route_helpers()
    return _installed_routes.list_installed_capabilities()


def get_installed_capability(capability_code: str):
    _sync_installed_route_helpers()
    return _installed_routes.get_installed_capability(capability_code)


def get_capability_ui_components(capability_code: str):
    _sync_installed_route_helpers()
    return _installed_routes.get_capability_ui_components(capability_code)


def _format_ui_component_for_response(
    capability_code: str,
    component: Dict[str, Any],
) -> Dict[str, Any]:
    return _core_format_ui_component_for_response(
        capability_code,
        component,
    )


def get_capability_workspace_tools(capability_code: str):
    _sync_installed_route_helpers()
    return _installed_routes.get_capability_workspace_tools(capability_code)


__all__ = [
    "router",
    "HTTPException",
    "PackResponse",
    "PackActivationStateResponse",
    "_pack_yaml_cache",
    "_pack_yaml_cache_time",
    "_pack_yaml_cache_lock",
    "_PACK_YAML_CACHE_TTL_SECONDS",
    "_PACK_SOURCE_PRIORITY",
    "_WORKSPACE_TOOL_ID_PATTERN",
    "_utc_now",
    "_load_manifest_file",
    "_safe_pack_code_variants",
    "_pack_root_candidates",
    "_candidate_pack_manifest_paths",
    "_map_pack_manifest_for_source",
    "_get_pack_meta_by_code",
    "_format_installed_capability",
    "_normalize_enabled_by_default",
    "_merge_unique_items",
    "_merge_pack_meta",
    "_map_runtime_manifest",
    "_is_pack_yaml_cache_fresh",
    "_scan_pack_yaml_files_uncached",
    "_scan_pack_yaml_files",
    "_get_installed_pack_ids",
    "_get_enabled_pack_ids",
    "list_packs",
    "enable_pack",
    "disable_pack",
    "list_installed_packs",
    "get_pack_activation_state",
    "list_enabled_packs",
    "list_installed_capabilities",
    "get_installed_capability",
    "get_capability_ui_components",
    "_format_ui_component_for_response",
    "get_capability_workspace_tools",
]
