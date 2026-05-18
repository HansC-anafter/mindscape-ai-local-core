import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from backend.app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir
from backend.app.services.stores.installed_packs_store import InstalledPacksStore

logger = logging.getLogger(__name__)
installed_packs_store = InstalledPacksStore()


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _load_manifest_file(manifest_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            pack_meta = yaml.safe_load(f)
            if pack_meta and isinstance(pack_meta, dict):
                pack_meta["_file_path"] = str(manifest_path)
                # Resolve external schema_path references in tool definitions
                from backend.app.services.manifest_utils import (
                    resolve_tool_schema_paths,
                )

                resolve_tool_schema_paths(pack_meta, manifest_path.parent)
                return pack_meta
    except Exception as e:
        logger.warning(f"Failed to load pack file {manifest_path}: {e}")
    return None


_pack_yaml_cache = None
_pack_yaml_cache_time = 0
_pack_yaml_cache_lock = threading.Lock()
_PACK_YAML_CACHE_TTL_SECONDS = 60

_PACK_SOURCE_PRIORITY = {
    "legacy_pack_yaml": 1,
    "capability_manifest": 2,
    "feature_manifest": 3,
}
_WORKSPACE_TOOL_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


def _safe_pack_code_variants(capability_code: str) -> List[str]:
    raw_variants = [
        capability_code,
        capability_code.replace("-", "_"),
        capability_code.replace("_", "-"),
    ]
    variants: List[str] = []
    seen = set()
    for variant in raw_variants:
        if not variant or Path(variant).name != variant or variant in seen:
            continue
        seen.add(variant)
        variants.append(variant)
    return variants


def _pack_root_candidates(base_dir: Path, child_path: str) -> List[Path]:
    return [
        base_dir / child_path,
        Path("/app/backend") / child_path,
        base_dir / "backend" / child_path,
    ]


def _candidate_pack_manifest_paths(
    capability_code: str,
    base_dir: Optional[Path] = None,
) -> List[tuple[Path, str, str]]:
    base_dir = base_dir or Path(__file__).parent.parent.parent.parent.parent
    candidates: List[tuple[Path, str, str]] = []

    for variant in _safe_pack_code_variants(capability_code):
        for root in _pack_root_candidates(base_dir, "app/capabilities"):
            candidates.append(
                (root / variant / "manifest.yaml", "capability_manifest", variant)
            )
        for root in _pack_root_candidates(base_dir, "features"):
            candidates.append((root / variant / "manifest.yaml", "feature_manifest", variant))
        for root in _pack_root_candidates(base_dir, "packs"):
            candidates.append((root / f"{variant}.yaml", "legacy_pack_yaml", variant))

    deduped: List[tuple[Path, str, str]] = []
    seen = set()
    for path, source_kind, default_id in candidates:
        marker = (str(path), source_kind)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append((path, source_kind, default_id))
    return deduped


def _map_pack_manifest_for_source(
    manifest_path: Path,
    source_kind: str,
    default_id: str,
) -> Optional[Dict[str, Any]]:
    meta = _load_manifest_file(manifest_path)
    if not meta:
        return None

    if source_kind == "legacy_pack_yaml":
        meta["_source_kind"] = source_kind
        return meta

    return _map_runtime_manifest(
        meta,
        default_id=default_id,
        manifest_path=manifest_path,
        source_kind=source_kind,
    )


def _get_pack_meta_by_code(
    capability_code: str,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    variants = set(_safe_pack_code_variants(capability_code))
    if not variants:
        return None

    merged_by_id: Dict[str, Dict[str, Any]] = {}
    for manifest_path, source_kind, default_id in _candidate_pack_manifest_paths(
        capability_code,
        base_dir,
    ):
        if not manifest_path.exists():
            continue

        meta = _map_pack_manifest_for_source(manifest_path, source_kind, default_id)
        if not meta:
            continue
        pack_id = meta.get("id") or meta.get("code")
        if not pack_id:
            continue
        existing = merged_by_id.get(pack_id)
        merged_by_id[pack_id] = _merge_pack_meta(existing, meta) if existing else meta

    for meta in merged_by_id.values():
        if meta.get("id") in variants or meta.get("code") in variants:
            return meta

    for meta in _scan_pack_yaml_files(base_dir):
        if meta.get("id") in variants or meta.get("code") in variants:
            return meta
    return None


def _format_installed_capability(pack_meta: Dict[str, Any]) -> Dict[str, Any]:
    pack_id = pack_meta.get("id")
    return {
        "id": pack_id,
        "code": pack_meta.get("code", pack_id),
        "display_name": pack_meta.get("name", pack_id),
        "version": pack_meta.get("version", "1.0.0"),
        "description": pack_meta.get("description", ""),
        "scope": pack_meta.get("scope", "global"),
        "ui_components": pack_meta.get("ui_components", []),
    }


def _normalize_enabled_by_default(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _merge_unique_items(left: Any, right: Any) -> List[Any]:
    merged: List[Any] = []
    seen = set()
    for group in (left or [], right or []):
        if not isinstance(group, list):
            continue
        for item in group:
            marker = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
    return merged


def _merge_pack_meta(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    existing_priority = _PACK_SOURCE_PRIORITY.get(
        existing.get("_source_kind", "legacy_pack_yaml"), 0
    )
    candidate_priority = _PACK_SOURCE_PRIORITY.get(
        candidate.get("_source_kind", "legacy_pack_yaml"), 0
    )

    primary = candidate if candidate_priority >= existing_priority else existing
    secondary = existing if primary is candidate else candidate

    merged = dict(primary)
    merged["routes"] = _merge_unique_items(
        secondary.get("routes"), primary.get("routes")
    )
    merged["playbooks"] = _merge_unique_items(
        secondary.get("playbooks"), primary.get("playbooks")
    )
    merged["tools"] = _merge_unique_items(
        secondary.get("tools"), primary.get("tools")
    )
    merged["ui_components"] = _merge_unique_items(
        secondary.get("ui_components"), primary.get("ui_components")
    )

    for key in ("description", "name", "display_name", "version", "enabled_by_default"):
        if merged.get(key) in (None, "", []):
            merged[key] = secondary.get(key)
    if not merged.get("_file_path"):
        merged["_file_path"] = secondary.get("_file_path")
    merged["enabled_by_default"] = _normalize_enabled_by_default(
        merged.get("enabled_by_default")
    )
    return merged


def _map_runtime_manifest(
    meta: Dict[str, Any],
    *,
    default_id: str,
    manifest_path: Path,
    source_kind: str,
) -> Dict[str, Any]:
    code = meta.get("code") or meta.get("id") or default_id
    name = meta.get("display_name") or meta.get("name") or code
    description = meta.get("description", "")

    playbooks = []
    for pb in meta.get("playbooks", []):
        if isinstance(pb, dict) and pb.get("code"):
            playbooks.append(pb["code"])
        elif isinstance(pb, str):
            playbooks.append(pb)

    mapped = {
        "id": code,
        "code": code,
        "name": name,
        "description": description,
        "version": meta.get("version", "1.0.0"),
        "enabled_by_default": _normalize_enabled_by_default(
            meta.get("enabled_by_default")
        ),
        "playbooks": playbooks,
        "ui_components": meta.get("ui_components", []),
        "_file_path": str(manifest_path),
        "_source_kind": source_kind,
    }
    for key, value in meta.items():
        if key not in mapped and key != "_file_path":
            mapped[key] = value
    return mapped


def _is_pack_yaml_cache_fresh(now: Optional[float] = None) -> bool:
    if _pack_yaml_cache is None:
        return False
    now = time.time() if now is None else now
    return (now - _pack_yaml_cache_time) < _PACK_YAML_CACHE_TTL_SECONDS


def _scan_pack_yaml_files_uncached(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan all installed capabilities and return their manifest data."""
    packs_by_id: Dict[str, Dict[str, Any]] = {}

    # Get packs directory
    # In Docker: /app/backend/app/routes/core/capability_packs.py -> /app/backend/packs
    # In local: backend/app/routes/core/capability_packs.py -> backend/packs
    base_dir = base_dir or Path(__file__).parent.parent.parent.parent.parent
    packs_dir = base_dir / "packs"
    legacy_packs_dir: Optional[Path] = None

    # If packs directory doesn't exist at calculated path, try alternative locations
    if packs_dir.exists():
        legacy_packs_dir = packs_dir
    else:
        # Try /app/backend/packs (Docker)
        alt_path = Path("/app/backend/packs")
        if alt_path.exists():
            legacy_packs_dir = alt_path
        else:
            # Try backend/packs (local dev)
            alt_path = base_dir / "backend" / "packs"
            if alt_path.exists():
                legacy_packs_dir = alt_path
            else:
                logger.warning(
                    f"Packs directory not found. Tried: {base_dir / 'packs'}, {Path('/app/backend/packs')}, {base_dir / 'backend' / 'packs'}"
                )

    # Scan for .yaml files
    if legacy_packs_dir is not None:
        for pack_file in legacy_packs_dir.glob("*.yaml"):
            meta = _load_manifest_file(pack_file)
            if meta:
                meta["_source_kind"] = "legacy_pack_yaml"
                pack_id = meta.get("id") or meta.get("code")
                if not pack_id:
                    continue
                existing = packs_by_id.get(pack_id)
                packs_by_id[pack_id] = (
                    _merge_pack_meta(existing, meta) if existing else meta
                )

    # Scan installed capabilities from backend/app/capabilities/
    capabilities_dir = base_dir / "app" / "capabilities"
    if not capabilities_dir.exists():
        alt_paths = [
            Path("/app/backend/app/capabilities"),  # Docker
            base_dir / "backend" / "app" / "capabilities",  # Local dev
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                capabilities_dir = alt_path
                break

    if capabilities_dir.exists():
        for cap_dir in capabilities_dir.iterdir():
            if not cap_dir.is_dir() or is_ignored_runtime_pack_dir(cap_dir.name):
                continue
            manifest_path = cap_dir / "manifest.yaml"
            if manifest_path.exists():
                meta = _load_manifest_file(manifest_path)
                if not meta:
                    continue
                meta_mapped = _map_runtime_manifest(
                    meta,
                    default_id=cap_dir.name,
                    manifest_path=manifest_path,
                    source_kind="capability_manifest",
                )
                pack_id = meta_mapped["id"]
                existing = packs_by_id.get(pack_id)
                packs_by_id[pack_id] = (
                    _merge_pack_meta(existing, meta_mapped)
                    if existing
                    else meta_mapped
                )

    features_dir = base_dir / "features"
    if not features_dir.exists():
        alt_paths = [
            Path("/app/backend/features"),
            base_dir / "backend" / "features",
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                features_dir = alt_path
                break

    if features_dir.exists():
        for feature_dir in features_dir.iterdir():
            if not feature_dir.is_dir() or is_ignored_runtime_pack_dir(feature_dir.name):
                continue
            manifest_path = feature_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            meta = _load_manifest_file(manifest_path)
            if not meta:
                continue
            meta_mapped = _map_runtime_manifest(
                meta,
                default_id=feature_dir.name,
                manifest_path=manifest_path,
                source_kind="feature_manifest",
            )
            pack_id = meta_mapped["id"]
            existing = packs_by_id.get(pack_id)
            packs_by_id[pack_id] = (
                _merge_pack_meta(existing, meta_mapped) if existing else meta_mapped
            )

    return list(packs_by_id.values())


def _scan_pack_yaml_files(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan all installed capabilities and return their manifest data.
    Results are cached for 60 seconds to avoid repeated filesystem scans.
    """
    global _pack_yaml_cache, _pack_yaml_cache_time
    if base_dir is not None:
        return _scan_pack_yaml_files_uncached(base_dir)

    if _is_pack_yaml_cache_fresh():
        return _pack_yaml_cache

    with _pack_yaml_cache_lock:
        if _is_pack_yaml_cache_fresh():
            return _pack_yaml_cache
        packs = _scan_pack_yaml_files_uncached()
        _pack_yaml_cache = packs
        _pack_yaml_cache_time = time.time()
        return packs


def _get_installed_pack_ids() -> set:
    """Get set of installed pack IDs from database"""
    return set(installed_packs_store.list_installed_pack_ids())


def _get_enabled_pack_ids() -> set:
    """Get set of enabled pack IDs from database"""
    return set(installed_packs_store.list_enabled_pack_ids())
