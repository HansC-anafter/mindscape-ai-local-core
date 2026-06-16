"""Helpers for capability API runtime reactivation."""

from __future__ import annotations

import importlib
import sys
from typing import Any, Iterable

from fastapi import FastAPI

from backend.app.services.capability_api_loader import (
    _descriptor_state_key,
    _get_runtime_state,
    build_descriptor_registered_prefixes,
)


def _dedupe_non_empty(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = str(value or "").strip().rstrip("/")
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        deduped.append(clean_value)
    return deduped


def _capability_module_prefixes(capability_code: str) -> list[str]:
    clean_code = capability_code.strip()
    if not clean_code:
        return []
    return [
        clean_code,
        f"capabilities.{clean_code}",
        f"app.capabilities.{clean_code}",
    ]


def _remove_capability_routes(
    app: FastAPI,
    *,
    path_prefixes: list[str],
    module_prefixes: list[str],
) -> int:
    kept_routes = []
    removed_count = 0
    for route in app.router.routes:
        route_path = str(getattr(route, "path", "") or "").rstrip("/")
        endpoint = getattr(route, "endpoint", None)
        endpoint_module = str(getattr(endpoint, "__module__", "") or "")
        matches_path = any(
            route_path == prefix or route_path.startswith(f"{prefix}/")
            for prefix in path_prefixes
        )
        matches_module = any(
            endpoint_module == prefix or endpoint_module.startswith(f"{prefix}.")
            for prefix in module_prefixes
        )
        if matches_path or matches_module:
            removed_count += 1
            continue
        kept_routes.append(route)
    if removed_count:
        app.router.routes = kept_routes
    return removed_count


def _purge_capability_modules(module_prefixes: list[str]) -> int:
    purged = 0
    for module_name in list(sys.modules):
        if any(
            module_name == prefix or module_name.startswith(f"{prefix}.")
            for prefix in module_prefixes
        ):
            purged += 1
            sys.modules.pop(module_name, None)
    importlib.invalidate_caches()
    return purged


def prepare_capability_for_reactivation(
    *,
    app: FastAPI,
    capability_code: str,
    descriptors: Iterable[Any],
) -> dict[str, Any]:
    """Clear route/module state so explicit activation loads fresh code."""

    descriptor_list = list(descriptors)
    state = _get_runtime_state(app)
    path_prefixes = _dedupe_non_empty(
        [
            *(state.get("prefixes_by_capability", {}).get(capability_code) or []),
            *(
                prefix
                for descriptor in descriptor_list
                for prefix in build_descriptor_registered_prefixes(descriptor)
            ),
        ]
    )
    module_prefixes = _capability_module_prefixes(capability_code)
    removed_routes = _remove_capability_routes(
        app,
        path_prefixes=path_prefixes,
        module_prefixes=module_prefixes,
    )
    purged_modules = _purge_capability_modules(module_prefixes)

    registered_descriptor_keys = state.setdefault("registered_descriptor_keys", set())
    for descriptor in descriptor_list:
        registered_descriptor_keys.discard(_descriptor_state_key(descriptor))

    activated_capabilities = state.setdefault("activated_capabilities", set())
    activated_capabilities.discard(capability_code)

    return {
        "removed_routes": removed_routes,
        "purged_modules": purged_modules,
        "path_prefixes": path_prefixes,
        "module_prefixes": module_prefixes,
    }


__all__ = ["prepare_capability_for_reactivation"]
