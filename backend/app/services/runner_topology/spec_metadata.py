"""Runner metadata extracted from installed capability playbook specs."""

from __future__ import annotations

import copy
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.services.contract_variants import select_exact_input_variant

logger = logging.getLogger(__name__)

_EXECUTION_PROFILE_KEYS = (
    "resource_class",
    "queue_partition",
    "queue_shard",
    "task_family",
    "managed_runner_role",
    "fairness_lane_key",
    "runner_profile_hint",
    "runtime_affinity",
    "runner_timeout_seconds",
    "resource_requirements",
    "resource_requirement_variants",
    "runner_metadata_variants",
    "trace_runner_heartbeat",
    "no_progress_watchdog",
    "runner_dependencies",
    "dependency_resolver",
)


def _capability_registry():
    try:
        from backend.app.services.capability_registry import get_registry, load_capabilities
    except Exception:
        from app.services.capability_registry import get_registry, load_capabilities

    registry = get_registry()
    try:
        if not registry.list_capabilities():
            load_capabilities()
    except Exception:
        pass
    return registry


def _normalize_playbook_entry(entry: Any) -> Optional[dict[str, Any]]:
    return entry if isinstance(entry, dict) else None


def _read_spec_json(spec_path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read playbook spec metadata from %s: %s", spec_path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _extract_runner_metadata_from_spec(
    spec: dict[str, Any],
    *,
    capability_code: Optional[str],
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if capability_code:
        metadata["capability_code"] = capability_code

    execution_profile = spec.get("execution_profile")
    if isinstance(execution_profile, dict):
        for key in _EXECUTION_PROFILE_KEYS:
            value = execution_profile.get(key)
            if value is not None:
                metadata[key] = copy.deepcopy(value)

    concurrency = spec.get("concurrency")
    if isinstance(concurrency, dict):
        metadata["concurrency"] = copy.deepcopy(concurrency)

    lifecycle_hooks = spec.get("lifecycle_hooks")
    if isinstance(lifecycle_hooks, dict):
        metadata["lifecycle_hooks"] = copy.deepcopy(lifecycle_hooks)

    return metadata


@lru_cache(maxsize=512)
def resolve_installed_playbook_runner_metadata(playbook_code: str) -> Dict[str, Any]:
    """Return runner metadata declared by an installed capability playbook spec."""
    normalized_code = str(playbook_code or "").strip()
    if not normalized_code:
        return {}

    try:
        registry = _capability_registry()
        for capability_code in registry.list_capabilities():
            capability = registry.get_capability(capability_code) or {}
            manifest = capability.get("manifest") or {}
            directory = capability.get("directory")
            if not isinstance(directory, Path):
                directory = Path(directory) if directory else None

            for raw_entry in manifest.get("playbooks", []) or []:
                entry = _normalize_playbook_entry(raw_entry)
                if not entry or str(entry.get("code") or "").strip() != normalized_code:
                    continue

                spec_rel = str(entry.get("spec_path") or "").strip()
                if not spec_rel or directory is None:
                    return {"capability_code": capability_code}

                spec = _read_spec_json((directory / spec_rel).resolve())
                if not spec:
                    return {"capability_code": capability_code}

                return _extract_runner_metadata_from_spec(
                    spec,
                    capability_code=capability_code,
                )
    except Exception as exc:
        logger.debug(
            "Failed to resolve installed playbook runner metadata for %s: %s",
            normalized_code,
            exc,
        )
    return {}


@lru_cache(maxsize=1)
def iter_installed_playbook_runner_metadata() -> tuple[tuple[str, Dict[str, Any]], ...]:
    """Return runner metadata for every installed playbook spec."""
    rows: list[tuple[str, Dict[str, Any]]] = []
    try:
        registry = _capability_registry()
        for capability_code in registry.list_capabilities():
            capability = registry.get_capability(capability_code) or {}
            manifest = capability.get("manifest") or {}
            directory = capability.get("directory")
            if not isinstance(directory, Path):
                directory = Path(directory) if directory else None

            for raw_entry in manifest.get("playbooks", []) or []:
                entry = _normalize_playbook_entry(raw_entry)
                playbook_code = str((entry or {}).get("code") or "").strip()
                if not entry or not playbook_code:
                    continue

                metadata: Dict[str, Any] = {"capability_code": capability_code}
                spec_rel = str(entry.get("spec_path") or "").strip()
                if spec_rel and directory is not None:
                    spec = _read_spec_json((directory / spec_rel).resolve())
                    if spec:
                        metadata = _extract_runner_metadata_from_spec(
                            spec,
                            capability_code=capability_code,
                        )
                metadata.setdefault("capability_code", capability_code)
                metadata.setdefault("playbook_code", playbook_code)
                rows.append((playbook_code, metadata))
    except Exception as exc:
        logger.debug("Failed to iterate installed playbook runner metadata: %s", exc)
    return tuple(rows)


def merge_runner_metadata_into_context(
    execution_context: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
    *,
    playbook_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge spec-declared runner metadata without overriding explicit context."""
    context = dict(execution_context) if isinstance(execution_context, dict) else {}
    if playbook_code and not context.get("playbook_code"):
        context["playbook_code"] = playbook_code

    if not isinstance(metadata, dict) or not metadata:
        return context

    metadata = resolve_runner_metadata_variant(metadata, context)
    merged = dict(context)
    for key, value in metadata.items():
        if key == "runner_metadata_variants":
            continue
        if key == "concurrency":
            declared = value if isinstance(value, dict) else {}
            explicit = context.get("concurrency") if isinstance(context.get("concurrency"), dict) else {}
            if declared or explicit:
                merged["concurrency"] = {
                    **copy.deepcopy(declared),
                    **copy.deepcopy(explicit),
                }
            continue
        if key not in merged or merged.get(key) is None:
            merged[key] = copy.deepcopy(value)
    return merged


def resolve_runner_metadata_variant(
    metadata: Dict[str, Any],
    execution_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply at most one exact-input runner metadata overlay."""

    base = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
    context = execution_context if isinstance(execution_context, dict) else {}
    inputs = context.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    selected = select_exact_input_variant(
        base.get("runner_metadata_variants"),
        inputs=inputs,
        payload_key="metadata",
        contract_label="runner metadata",
    )
    base.update(selected)
    return base
