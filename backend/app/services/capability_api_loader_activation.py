"""Runtime activation flows for capability API routers."""

import logging
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, FastAPI

from .capability_api_loader_core import CapabilityAPILoader
from .capability_api_loader_state import (
    _capability_registration_complete,
    _descriptor_state_key,
    _extract_registered_routes_from_app,
    _get_runtime_state,
    _remove_routes_for_prefixes,
    build_descriptor_registered_prefixes,
    load_manifest_for_descriptor,
    seed_capability_api_descriptors,
)
from .capability_api_loader_types import CapabilityAPIDescriptor
from .tools.tool_availability_explanation import (
    build_capability_api_activation_explanation,
)

logger = logging.getLogger(__name__)


def _record_activation_explanation(
    state: dict[str, Any],
    *,
    descriptor: CapabilityAPIDescriptor,
    status: str,
    reason: str,
    expected_routes: set[tuple[str, str]] | None = None,
    conflicts: list[tuple[str, str]] | None = None,
) -> None:
    entries = list(state.get("capability_api_activation_explanations") or [])
    entries.append(
        build_capability_api_activation_explanation(
            capability_code=descriptor.capability_code,
            status=status,
            reason=reason,
            expected_routes=expected_routes,
            conflicts=conflicts,
        )
    )
    state["capability_api_activation_explanations"] = entries[-100:]


def activate_seeded_capability_apis(
    *,
    app: FastAPI,
    descriptors: Optional[List[CapabilityAPIDescriptor]] = None,
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False,
    route_collector: Optional[List[Any]] = None,
    activation_mode: str = "startup_eager",
    activation_service: Optional[Any] = None,
    installed_packs_store: Optional[Any] = None,
) -> List[APIRouter]:
    state = _get_runtime_state(app)
    existing_activated = set(state.get("activated_capabilities") or set())
    if descriptors is None:
        descriptors = state.get("descriptors") or seed_capability_api_descriptors(
            app=app,
            remote_capabilities_dir=remote_capabilities_dir,
            allowlist=allowlist,
            enable_all=enable_all,
            installed_packs_store=installed_packs_store,
        )

    loader = CapabilityAPILoader(
        remote_capabilities_dir=remote_capabilities_dir,
        allowlist=allowlist,
        enable_all=enable_all,
        installed_packs_store=installed_packs_store,
    )
    loader.registered_routes = _extract_registered_routes_from_app(app)

    routers: List[APIRouter] = []
    processed_capabilities = {descriptor.capability_code for descriptor in descriptors}
    registered_descriptor_keys = state.setdefault("registered_descriptor_keys", set())
    for descriptor in descriptors:
        descriptor_key = _descriptor_state_key(descriptor)
        descriptor_marked_registered = descriptor_key in registered_descriptor_keys
        manifest = load_manifest_for_descriptor(descriptor)
        manifest_path = (
            descriptor.manifest_path if descriptor.manifest_path.exists() else None
        )
        try:
            router = loader.load_api_router_from_capability_def(
                descriptor.capability_code,
                descriptor.capability_dir,
                descriptor.cap_def,
            )
            if router is None:
                continue
            manifest_prefix = descriptor.cap_def.get("prefix", "") or ""
            expected_routes = loader.extract_routes_from_router(router, manifest_prefix)
            existing_routes = set(loader.registered_routes)
            if descriptor_marked_registered:
                if expected_routes and expected_routes.issubset(existing_routes):
                    _record_activation_explanation(
                        state,
                        descriptor=descriptor,
                        status="skipped",
                        reason="descriptor_routes_already_registered",
                        expected_routes=expected_routes,
                    )
                    logger.debug(
                        "Skipping capability API router for %s; descriptor routes are already registered",
                        descriptor.capability_code,
                    )
                    continue
                registered_descriptor_keys.discard(descriptor_key)
                logger.warning(
                    "Re-registering stale capability API descriptor for %s; descriptor was marked registered but routes are absent",
                    descriptor.capability_code,
                )
            if expected_routes and expected_routes.issubset(existing_routes):
                registered_descriptor_keys.add(descriptor_key)
                _record_activation_explanation(
                    state,
                    descriptor=descriptor,
                    status="skipped",
                    reason="all_descriptor_routes_already_registered",
                    expected_routes=expected_routes,
                )
                logger.debug(
                    "Skipping capability API router for %s; all descriptor routes already registered",
                    descriptor.capability_code,
                )
                continue

            conflicts = sorted(expected_routes & existing_routes)
            missing_routes = expected_routes - existing_routes
            if conflicts and missing_routes:
                removed_count = _remove_routes_for_prefixes(
                    app,
                    build_descriptor_registered_prefixes(descriptor, router),
                )
                if removed_count:
                    logger.warning(
                        "Replacing stale capability API routes for %s; removed=%d missing=%d",
                        descriptor.capability_code,
                        removed_count,
                        len(missing_routes),
                    )
                    registered_descriptor_keys.discard(descriptor_key)
                    loader.registered_routes = _extract_registered_routes_from_app(app)
                    existing_routes = set(loader.registered_routes)
                    conflicts = sorted(expected_routes & existing_routes)
            if conflicts:
                _record_activation_explanation(
                    state,
                    descriptor=descriptor,
                    status="failed",
                    reason="route_conflict",
                    expected_routes=expected_routes,
                    conflicts=conflicts,
                )
                conflict_details = ", ".join(
                    f"{method} {path}" for method, path in conflicts
                )
                raise ValueError(
                    f"Route conflict detected for capability {descriptor.capability_code}: "
                    f"Routes {conflict_details} are already registered. "
                    "Please check router prefix and path definitions."
                )

            before_routes = list(app.router.routes)
            prefix = descriptor.cap_def.get("prefix")
            if prefix:
                app.include_router(router, prefix=prefix)
                logger.info(
                    "Registered capability API router for %s with prefix: %s",
                    descriptor.capability_code,
                    prefix,
                )
            else:
                app.include_router(router)
                logger.info(
                    "Registered capability API router for %s with prefix: %s",
                    descriptor.capability_code,
                    getattr(router, "prefix", "none"),
                )
            if route_collector is not None:
                after_routes = list(app.router.routes)
                route_collector.extend(after_routes[len(before_routes) :])
            loader.loaded_routers.append(
                (router, descriptor.capability_code, descriptor.cap_def)
            )
            loader.registered_routes.update(expected_routes)
            if activation_service is not None:
                activation_service.record_activation_succeeded(
                    pack_id=descriptor.capability_code,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    activation_mode=activation_mode,
                    registered_prefixes=build_descriptor_registered_prefixes(
                        descriptor, router
                    ),
                )
            _record_activation_explanation(
                state,
                descriptor=descriptor,
                status="activated",
                reason="routes_registered",
                expected_routes=expected_routes,
            )
            routers.append(router)
            registered_descriptor_keys.add(descriptor_key)
        except Exception as exc:
            if activation_service is not None:
                activation_service.record_activation_failed(
                    pack_id=descriptor.capability_code,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    activation_mode=activation_mode,
                    error=str(exc),
                    registered_prefixes=build_descriptor_registered_prefixes(
                        descriptor
                    ),
                )
            raise

    activated_capabilities = {
        capability_code
        for capability_code in processed_capabilities
        if _capability_registration_complete(app, capability_code)
    }
    state["activated_capabilities"] = existing_activated | activated_capabilities
    return routers


def activate_capability_api_code(
    *,
    app: FastAPI,
    capability_code: str,
    route_collector: Optional[List[Any]] = None,
    activation_mode: str = "request_activate",
    activation_service: Optional[Any] = None,
    force_refresh: bool = False,
) -> List[APIRouter]:
    state = _get_runtime_state(app)
    activation_lock = state["activation_lock"]
    with activation_lock:
        capability_already_activated = capability_code in state.get(
            "activated_capabilities", set()
        )
        if (
            not force_refresh
            and capability_already_activated
            and _capability_registration_complete(app, capability_code)
        ):
            return []
        descriptors = (
            state.get("descriptors_by_capability", {}).get(capability_code) or []
        )
        if not descriptors:
            return []
        return activate_seeded_capability_apis(
            app=app,
            descriptors=descriptors,
            route_collector=route_collector,
            activation_mode=activation_mode,
            activation_service=activation_service,
        )


def load_capability_apis(
    app: Optional[FastAPI] = None,
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False,
    route_collector: Optional[List[Any]] = None,
    activation_mode: str = "manual_load",
    activation_service: Optional[Any] = None,
    installed_packs_store: Optional[Any] = None,
) -> List[APIRouter]:
    """
    Load and return all capability API routers.

    Args:
        remote_capabilities_dir: Explicit capabilities directory override for
            compatibility and tests. Runtime discovery does not read environment-
            configured source trees.
        allowlist: Optional list of capability codes to load.
        enable_all: If True, load all capabilities.

    Returns:
        List of APIRouter instances.
    """
    if app is None:
        loader = CapabilityAPILoader(
            remote_capabilities_dir,
            allowlist,
            enable_all,
            installed_packs_store=installed_packs_store,
        )
        return loader.load_all_capability_apis()

    descriptors = seed_capability_api_descriptors(
        app=app,
        remote_capabilities_dir=remote_capabilities_dir,
        allowlist=allowlist,
        enable_all=enable_all,
        installed_packs_store=installed_packs_store,
    )
    return activate_seeded_capability_apis(
        app=app,
        descriptors=descriptors,
        remote_capabilities_dir=remote_capabilities_dir,
        allowlist=allowlist,
        enable_all=enable_all,
        route_collector=route_collector,
        activation_mode=activation_mode,
        activation_service=activation_service,
        installed_packs_store=installed_packs_store,
    )


__all__ = [
    "activate_seeded_capability_apis",
    "activate_capability_api_code",
    "load_capability_apis",
]
