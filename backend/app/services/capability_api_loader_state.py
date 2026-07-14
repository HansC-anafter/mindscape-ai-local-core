"""Runtime state helpers for capability API activation."""

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, FastAPI
from starlette.routing import Mount, Route

from .capability_api_loader_core import CapabilityAPILoader
from .capability_api_loader_types import (
    _APP_STATE_KEY,
    _DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST,
    _VALID_ACTIVATION_POLICIES,
    CapabilityAPIDescriptor,
)

logger = logging.getLogger(__name__)


def get_capability_api_activation_policy() -> str:
    # Default to request-time activation so backend startup is not blocked by
    # importing every capability API router up front.
    policy = (os.getenv("CAPABILITY_API_ACTIVATION_POLICY") or "seed_only").strip()
    if policy not in _VALID_ACTIVATION_POLICIES:
        logger.warning(
            "Unknown CAPABILITY_API_ACTIVATION_POLICY=%s; falling back to seed_only",
            policy,
        )
        return "seed_only"
    return policy


def get_capability_api_startup_activation_allowlist() -> List[str]:
    raw = os.getenv("CAPABILITY_API_STARTUP_ALLOWLIST")
    if raw is None:
        return list(_DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST)

    allowlist: List[str] = []
    seen: Set[str] = set()
    for item in raw.split(","):
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        allowlist.append(normalized)
    return allowlist


def group_capability_api_descriptors(
    descriptors: List[CapabilityAPIDescriptor],
) -> Dict[str, List[CapabilityAPIDescriptor]]:
    grouped: Dict[str, List[CapabilityAPIDescriptor]] = {}
    for descriptor in descriptors:
        grouped.setdefault(descriptor.capability_code, []).append(descriptor)
    return grouped


def _get_runtime_state(app: FastAPI) -> Dict[str, Any]:
    state = getattr(app.state, _APP_STATE_KEY, None)
    if state is None:
        state = {
            "descriptors": [],
            "descriptors_by_capability": {},
            "activated_capabilities": set(),
            "prefixes_by_capability": {},
            "sorted_prefix_entries": [],
            "registered_descriptor_keys": set(),
            "activation_lock": threading.RLock(),
            "seed_params": {},
        }
        setattr(app.state, _APP_STATE_KEY, state)
    return state


def _descriptor_state_key(descriptor: CapabilityAPIDescriptor) -> str:
    return "|".join(
        [
            descriptor.capability_code,
            descriptor.cap_def.get("code", "") or "",
            descriptor.cap_def.get("path", "") or "",
            descriptor.cap_def.get("prefix", "") or "",
        ]
    )


def _extract_registered_routes_from_app(app: FastAPI) -> Set[Tuple[str, str]]:
    routes: Set[Tuple[str, str]] = set()

    def extract_from_route(route: Route, prefix: str = ""):
        methods = getattr(route, "methods", set())
        path = prefix + route.path
        for method in methods:
            if method != "HEAD":
                routes.add((method.upper(), path))

    def extract_from_mount(mount: Mount, prefix: str = ""):
        mount_path = prefix + mount.path
        for route in mount.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                extract_from_route(route, mount_path)
            elif isinstance(route, Mount):
                extract_from_mount(route, mount_path)

    for route in app.router.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            extract_from_route(route)
        elif isinstance(route, Mount):
            extract_from_mount(route)
    return routes


def _remove_routes_for_prefixes(app: FastAPI, prefixes: List[str]) -> int:
    normalized_prefixes = [
        prefix.rstrip("/")
        for prefix in prefixes
        if isinstance(prefix, str) and prefix.strip()
    ]
    if not normalized_prefixes:
        return 0

    kept_routes = []
    removed_count = 0
    for route in app.router.routes:
        route_path = getattr(route, "path", "")
        should_remove = any(
            route_path == prefix or route_path.startswith(f"{prefix}/")
            for prefix in normalized_prefixes
        )
        if should_remove:
            removed_count += 1
            continue
        kept_routes.append(route)
    if removed_count:
        app.router.routes = kept_routes
    return removed_count


def _capability_registration_complete(app: FastAPI, capability_code: str) -> bool:
    state = _get_runtime_state(app)
    descriptors = state.get("descriptors_by_capability", {}).get(capability_code) or []
    if not descriptors:
        return False
    registered_descriptor_keys = state.get("registered_descriptor_keys", set())
    return all(
        _descriptor_state_key(descriptor) in registered_descriptor_keys
        for descriptor in descriptors
    )


def capability_api_registration_complete(
    app: FastAPI,
    capability_code: str,
) -> bool:
    """Return whether a seeded capability can serve requests without activation."""

    state = _get_runtime_state(app)
    return capability_code in state.get(
        "activated_capabilities", set()
    ) and _capability_registration_complete(app, capability_code)


def load_manifest_for_descriptor(descriptor: CapabilityAPIDescriptor) -> Dict[str, Any]:
    loader = CapabilityAPILoader(
        remote_capabilities_dir=descriptor.capability_dir.parent
    )
    return loader.load_manifest_document(descriptor.manifest_path)


def build_descriptor_registered_prefixes(
    descriptor: CapabilityAPIDescriptor, router: Optional[APIRouter] = None
) -> List[str]:
    prefixes: List[str] = []
    manifest_prefix = descriptor.cap_def.get("prefix", "") or ""
    router_prefix = getattr(router, "prefix", "") if router is not None else ""
    combined = f"{manifest_prefix}{router_prefix}"
    if combined:
        prefixes.append(combined)
    elif manifest_prefix:
        prefixes.append(manifest_prefix)
    elif router_prefix:
        prefixes.append(router_prefix)
    return prefixes


def seed_capability_api_descriptors(
    *,
    app: FastAPI,
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False,
    installed_packs_store: Optional[Any] = None,
) -> List[CapabilityAPIDescriptor]:
    loader = CapabilityAPILoader(
        remote_capabilities_dir=remote_capabilities_dir,
        allowlist=allowlist,
        enable_all=enable_all,
        installed_packs_store=installed_packs_store,
    )
    descriptors = loader.discover_capability_api_descriptors()
    state = _get_runtime_state(app)
    state["seed_params"] = {
        "remote_capabilities_dir": remote_capabilities_dir,
        "allowlist": allowlist,
        "enable_all": enable_all,
        "installed_packs_store": installed_packs_store,
    }
    grouped = group_capability_api_descriptors(descriptors)
    prefixes_by_capability: Dict[str, List[str]] = {}
    prefix_entries: List[Tuple[str, str]] = []
    for capability_code, descriptor_group in grouped.items():
        prefixes: List[str] = []
        for descriptor in descriptor_group:
            prefixes.extend(build_descriptor_registered_prefixes(descriptor))
        deduped: List[str] = []
        seen = set()
        for prefix in prefixes:
            if prefix and prefix not in seen:
                seen.add(prefix)
                deduped.append(prefix)
                prefix_entries.append((prefix, capability_code))
        prefixes_by_capability[capability_code] = deduped
    state["descriptors"] = descriptors
    state["descriptors_by_capability"] = grouped
    state["activated_capabilities"] = set()
    state["prefixes_by_capability"] = prefixes_by_capability
    state["sorted_prefix_entries"] = sorted(
        prefix_entries,
        key=lambda item: len(item[0]),
        reverse=True,
    )
    state["registered_descriptor_keys"] = set()
    return descriptors


def refresh_seeded_capability_descriptors(
    app: FastAPI,
) -> List[CapabilityAPIDescriptor]:
    state = _get_runtime_state(app)
    seed_params = state.get("seed_params") or {}
    existing_activated = set(state.get("activated_capabilities") or set())
    existing_registered = set(state.get("registered_descriptor_keys") or set())
    descriptors = seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=seed_params.get("remote_capabilities_dir"),
        allowlist=seed_params.get("allowlist"),
        enable_all=bool(seed_params.get("enable_all", False)),
        installed_packs_store=seed_params.get("installed_packs_store"),
    )
    state["activated_capabilities"] = set(state.get("activated_capabilities") or set())
    state["activated_capabilities"].update(existing_activated)
    state["registered_descriptor_keys"] = set(
        state.get("registered_descriptor_keys") or set()
    )
    state["registered_descriptor_keys"].update(existing_registered)
    return descriptors


def find_seeded_capability_for_path(app: FastAPI, path: str) -> Optional[str]:
    state = _get_runtime_state(app)
    for prefix, capability_code in state.get("sorted_prefix_entries", []):
        normalized = prefix.rstrip("/")
        if not normalized:
            continue
        if path == normalized or path.startswith(f"{normalized}/"):
            return capability_code
    return None


__all__ = [
    "get_capability_api_activation_policy",
    "get_capability_api_startup_activation_allowlist",
    "group_capability_api_descriptors",
    "_get_runtime_state",
    "_descriptor_state_key",
    "_extract_registered_routes_from_app",
    "_remove_routes_for_prefixes",
    "_capability_registration_complete",
    "capability_api_registration_complete",
    "load_manifest_for_descriptor",
    "build_descriptor_registered_prefixes",
    "seed_capability_api_descriptors",
    "refresh_seeded_capability_descriptors",
    "find_seeded_capability_for_path",
]
