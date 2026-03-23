"""
Capability API Loader
Automatically loads and registers API routers from cloud capability packs

Supports:
- Router export contract (router_export: 'router' or 'get_router')
- enabled_by_default flag
- allowlist control
- Dev/Deploy mode path resolution
- Route conflict detection via (method, path) tuples
"""

from dataclasses import dataclass
import yaml
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import logging
import os
import threading
from fastapi import APIRouter, FastAPI
from starlette.routing import Route, Mount
from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir

logger = logging.getLogger(__name__)

_APP_STATE_KEY = "capability_api_loader_state"
_VALID_ACTIVATION_POLICIES = {"startup_eager", "seed_only"}


@dataclass(frozen=True)
class CapabilityAPIDescriptor:
    """Manifest-derived descriptor for a capability API module."""

    capability_code: str
    capability_dir: Path
    manifest_path: Path
    cap_def: Dict[str, Any]


class CapabilityAPILoader:
    """Loads and registers API routers from cloud capability manifests"""

    def __init__(
        self,
        remote_capabilities_dir: Optional[Path] = None,
        allowlist: Optional[List[str]] = None,
        enable_all: bool = False,
        installed_packs_store: Optional[Any] = None,
    ):
        """
        Initialize the API loader

        Args:
            remote_capabilities_dir: Path to remote capabilities directory
                If None, will try to resolve from environment or default path
            allowlist: Optional list of capability codes to load
                If None and enable_all=False, only enabled_by_default=True are loaded
            enable_all: If True, load all capabilities regardless of allowlist/enabled_by_default
        """
        self.remote_capabilities_dir = remote_capabilities_dir
        self.allowlist = set(allowlist) if allowlist else None
        self.enable_all = enable_all or os.getenv("ENABLE_ALL_CAPABILITIES") == "1"
        self.installed_packs_store = installed_packs_store
        self.loaded_routers: List[Tuple[APIRouter, str, Dict]] = []
        self.registered_routes: Set[Tuple[str, str]] = set()
        self._installed_pack_enablement: Optional[Dict[str, bool]] = None

    def find_remote_capabilities_dir(self) -> Optional[Path]:
        """
        Find remote capabilities directory with fallback strategies

        Deploy mode: Must be set via MINDSCAPE_REMOTE_CAPABILITIES_DIR env var
        """
        deployment_mode = os.getenv("DEPLOYMENT_MODE", "dev")
        is_production = deployment_mode.lower() in ("production", "prod", "deploy")

        env_dir = os.getenv("MINDSCAPE_REMOTE_CAPABILITIES_DIR")
        if env_dir:
            path = Path(env_dir)
            if path.exists():
                return path
            else:
                logger.warning(
                    f"Env MINDSCAPE_REMOTE_CAPABILITIES_DIR points to non-existent path: {env_dir}"
                )

        if is_production:
            raise ValueError(
                "DEPLOYMENT_MODE is set to production/deploy, but "
                "MINDSCAPE_REMOTE_CAPABILITIES_DIR is not set. "
                "Please set MINDSCAPE_REMOTE_CAPABILITIES_DIR environment variable."
            )

        if self.remote_capabilities_dir and self.remote_capabilities_dir.exists():
            return self.remote_capabilities_dir

        return None

    def load_manifest_capabilities(self, manifest_path: Path) -> List[Dict]:
        """
        Load APIs section from manifest.yaml

        Returns:
            List of API definitions from manifest
        """
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            apis = manifest.get("apis", [])
            if not isinstance(apis, list):
                return []

            return apis
        except Exception as e:
            logger.warning(f"Failed to load manifest from {manifest_path}: {e}")
            return []

    def resolve_capabilities_dir(self) -> Optional[Path]:
        """
        Resolve the capabilities directory to scan.

        Priority:
        1. local installed capabilities
        2. explicitly configured remote capabilities directory
        """
        local_capabilities_dir = Path("/app/backend/app/capabilities")
        remote_capabilities_dir = self.find_remote_capabilities_dir()

        if local_capabilities_dir.exists():
            logger.info(
                f"Using local installed capabilities directory: {local_capabilities_dir}"
            )
            return local_capabilities_dir

        if remote_capabilities_dir and remote_capabilities_dir.exists():
            logger.info(f"Using remote capabilities directory: {remote_capabilities_dir}")
            return remote_capabilities_dir

        logger.warning(
            "Neither local nor remote capabilities directory found. "
            "Skipping capability API loading."
        )
        return None

    def should_load_capability(self, capability_code: str, cap_def: Dict) -> bool:
        """
        Determine if a capability should be loaded based on allowlist and enabled_by_default

        Args:
            capability_code: Capability code
            cap_def: Capability definition from manifest

        Returns:
            True if should load, False otherwise
        """
        if self.enable_all:
            return True

        if self.allowlist is not None:
            return capability_code in self.allowlist

        enabled_from_db = self._get_installed_pack_enabled(capability_code)
        if enabled_from_db is not None:
            return enabled_from_db

        enabled_by_default = cap_def.get("enabled_by_default", True)
        return enabled_by_default

    def load_manifest_document(self, manifest_path: Path) -> Dict[str, Any]:
        """Load the full manifest document for activation bookkeeping."""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
            if isinstance(manifest, dict):
                return manifest
        except Exception as exc:
            logger.warning("Failed to load manifest document from %s: %s", manifest_path, exc)
        return {"code": manifest_path.parent.name}

    def _get_installed_pack_enabled(self, capability_code: str) -> Optional[bool]:
        if self._installed_pack_enablement is None:
            self._installed_pack_enablement = self._load_installed_pack_enablement()
        return self._installed_pack_enablement.get(capability_code)

    def _load_installed_pack_enablement(self) -> Dict[str, bool]:
        try:
            if self.installed_packs_store is None:
                from app.services.stores.installed_packs_store import InstalledPacksStore

                self.installed_packs_store = InstalledPacksStore()
            rows = self.installed_packs_store.list_installed_metadata()
            return {
                row["pack_id"]: bool(row.get("enabled"))
                for row in rows
                if row.get("pack_id")
            }
        except Exception as exc:
            logger.debug("Installed pack enablement unavailable; falling back to manifests: %s", exc)
            return {}

    def load_api_router_from_capability_def(
        self, capability_code: str, capability_dir: Path, cap_def: Dict
    ) -> Optional[APIRouter]:
        """
        Load API router from capability definition using router_export contract

        Args:
            capability_code: Capability code
            capability_dir: Directory containing the capability
            cap_def: Capability definition from manifest

        Returns:
            APIRouter instance if found, None otherwise
        """
        api_path = cap_def.get("path")
        if not api_path:
            logger.warning(
                f"Capability {cap_def.get('code', 'unknown')} in {capability_code} "
                "has no path defined"
            )
            return None

        api_file_path = capability_dir / api_path
        if not api_file_path.exists():
            logger.warning(f"API file not found for {capability_code}: {api_file_path}")
            return None

        capabilities_root = capability_dir.parent
        app_root = capabilities_root.parent
        backend_root = app_root.parent
        for path in (capabilities_root, app_root, backend_root):
            path_str = str(path)
            if path_str in sys.path:
                sys.path.remove(path_str)
            sys.path.insert(0, path_str)

        try:
            relative_path = api_file_path.relative_to(capabilities_root)
            module_parts = list(relative_path.parts[:-1])
            module_name_base = ".".join(module_parts)
            file_stem = api_file_path.stem
            module_name = f"{module_name_base}.{file_stem}"

            # Create module spec with proper package name to support relative imports
            # Use full package path like 'capabilities.brand_identity.api.cis_mapper_endpoints'
            spec = importlib.util.spec_from_file_location(module_name, api_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create module spec for {api_file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            # Set __package__ and __file__ to support relative imports
            if "." in module_name:
                module.__package__ = ".".join(module_name.split(".")[:-1])
            module.__file__ = str(api_file_path)
            # Ensure capability directory is in sys.path for relative imports
            if str(capability_dir) not in sys.path:
                sys.path.insert(0, str(capability_dir))
            spec.loader.exec_module(module)

            router_export = cap_def.get("router_export", "router")

            if router_export == "get_router":
                get_router_func = getattr(module, "get_router", None)
                if get_router_func is None:
                    logger.error(
                        f"router_export='get_router' but no get_router() function found "
                        f"in {api_file_path} for {capability_code}"
                    )
                    return None
                if not callable(get_router_func):
                    logger.error(
                        f"get_router in {api_file_path} is not callable for {capability_code}"
                    )
                    return None
                router = get_router_func()
            elif router_export == "router":
                router = getattr(module, "router", None)
            else:
                logger.error(
                    f"Invalid router_export value '{router_export}' for {capability_code}. "
                    "Must be 'router' or 'get_router'"
                )
                return None

            if router is None:
                logger.warning(
                    f"No router found in {api_file_path} for {capability_code} "
                    f"(router_export={router_export})"
                )
                return None

            if not isinstance(router, APIRouter):
                logger.warning(
                    f"Router in {api_file_path} is not an APIRouter instance for {capability_code}"
                )
                return None

            logger.info(
                f"Loaded API router from {capability_code}/{api_path} "
                f"(prefix: {router.prefix if hasattr(router, 'prefix') else 'none'})"
            )
            return router

        except Exception as e:
            logger.error(
                f"Failed to load API router from {api_file_path}: {e}", exc_info=True
            )
            return None

    def discover_capability_api_descriptors(self) -> List[CapabilityAPIDescriptor]:
        """
        Discover capability API descriptors from manifests without importing modules.
        """
        capabilities_dir = self.resolve_capabilities_dir()
        if capabilities_dir is None or not capabilities_dir.exists():
            return []

        descriptors: List[CapabilityAPIDescriptor] = []
        for capability_dir in capabilities_dir.iterdir():
            if not capability_dir.is_dir() or is_ignored_runtime_pack_dir(
                capability_dir.name
            ):
                continue

            capability_code = capability_dir.name
            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.debug(f"No manifest.yaml found in {capability_dir}, skipping")
                continue

            capabilities = self.load_manifest_capabilities(manifest_path)
            if not capabilities:
                logger.debug(
                    f"No capabilities defined in manifest for {capability_code}"
                )
                continue

            for cap_def in capabilities:
                if not isinstance(cap_def, dict):
                    continue
                if not self.should_load_capability(capability_code, cap_def):
                    logger.debug(
                        f"Skipping {capability_code} (not in allowlist and enabled_by_default=False)"
                    )
                    continue
                descriptors.append(
                    CapabilityAPIDescriptor(
                        capability_code=capability_code,
                        capability_dir=capability_dir,
                        manifest_path=manifest_path,
                        cap_def=cap_def,
                    )
                )

        logger.info(
            "Discovered %d capability API descriptor(s) from manifests", len(descriptors)
        )
        return descriptors

    def activate_capability_api_descriptor(
        self, descriptor: CapabilityAPIDescriptor
    ) -> Optional[APIRouter]:
        """
        Import and validate a capability API router from a discovered descriptor.
        """
        router = self.load_api_router_from_capability_def(
            descriptor.capability_code, descriptor.capability_dir, descriptor.cap_def
        )

        if not router:
            return None

        is_valid, conflicts = self.check_route_conflicts(
            router, descriptor.capability_code, descriptor.cap_def
        )
        if is_valid:
            self.loaded_routers.append(
                (router, descriptor.capability_code, descriptor.cap_def)
            )
            return router

        conflict_details = ", ".join([f"{m} {p}" for m, p in conflicts])
        raise ValueError(
            f"Route conflict detected for capability {descriptor.capability_code}: "
            f"Routes {conflict_details} are already registered. "
            f"Please check router prefix and path definitions."
        )

    def extract_routes_from_router(
        self, router: APIRouter, manifest_prefix: str = ""
    ) -> Set[Tuple[str, str]]:
        """
        Extract all (method, path) tuples from a router

        Args:
            router: APIRouter instance
            manifest_prefix: Prefix from manifest.yaml to prepend to all routes

        Returns:
            Set of (method, path) tuples
        """
        routes = set()

        def extract_from_route(route: Route, prefix: str = ""):
            methods = getattr(route, "methods", set())
            path = prefix + route.path
            for method in methods:
                if method != "HEAD":
                    routes.add((method.upper(), path))

        def extract_from_mount(mount: Mount, prefix: str = ""):
            mount_path = prefix + mount.path
            for route in mount.routes:
                if isinstance(route, Route):
                    extract_from_route(route, mount_path)
                elif isinstance(route, Mount):
                    extract_from_mount(route, mount_path)
                elif isinstance(route, APIRouter):
                    extract_from_mount(route, mount_path)

        router_prefix = getattr(router, "prefix", "") or ""
        base_prefix = manifest_prefix + router_prefix

        for route in router.routes:
            if isinstance(route, Route):
                extract_from_route(route, base_prefix)
            elif isinstance(route, Mount):
                extract_from_mount(route, base_prefix)
            elif isinstance(route, APIRouter):
                nested_prefix = getattr(route, "prefix", "") or ""
                full_prefix = base_prefix + nested_prefix
                for nested_route in route.routes:
                    if isinstance(nested_route, Route):
                        extract_from_route(nested_route, full_prefix)
                    elif isinstance(nested_route, Mount):
                        extract_from_mount(nested_route, full_prefix)

        return routes

    def check_route_conflicts(
        self, router: APIRouter, capability_code: str, cap_def: Dict
    ) -> Tuple[bool, List[Tuple[str, str]]]:
        """
        Check if router routes conflict with already registered routes

        Args:
            router: APIRouter to check
            capability_code: Capability code
            cap_def: Capability definition

        Returns:
            (is_valid, conflicts) where conflicts is list of conflicting (method, path) tuples
        """
        manifest_prefix = cap_def.get("prefix", "") or ""
        new_routes = self.extract_routes_from_router(router, manifest_prefix)
        conflicts = []

        for method, path in new_routes:
            if (method, path) in self.registered_routes:
                conflicts.append((method, path))

        if conflicts:
            return False, conflicts
        self.registered_routes.update(new_routes)
        return True, []

    def load_all_capability_apis(self) -> List[APIRouter]:
        """
        Load all API routers from cloud capabilities

        Returns:
            List of APIRouter instances
        """
        descriptors = self.discover_capability_api_descriptors()
        if not descriptors:
            return []

        loaded_routers = []
        for descriptor in descriptors:
            router = self.activate_capability_api_descriptor(descriptor)
            if router:
                loaded_routers.append(router)

        logger.info(f"Loaded {len(loaded_routers)} API routers from cloud capabilities")
        return loaded_routers


def discover_capability_api_descriptors(
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False,
) -> List[CapabilityAPIDescriptor]:
    """Discover capability API descriptors without importing modules."""
    loader = CapabilityAPILoader(remote_capabilities_dir, allowlist, enable_all)
    return loader.discover_capability_api_descriptors()


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
            "activation_lock": threading.Lock(),
        }
        setattr(app.state, _APP_STATE_KEY, state)
    return state


def load_manifest_for_descriptor(descriptor: CapabilityAPIDescriptor) -> Dict[str, Any]:
    loader = CapabilityAPILoader(remote_capabilities_dir=descriptor.capability_dir.parent)
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
    return descriptors


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

    routers: List[APIRouter] = []
    activated_capabilities: Set[str] = set()
    for descriptor in descriptors:
        manifest = load_manifest_for_descriptor(descriptor)
        manifest_path = descriptor.manifest_path if descriptor.manifest_path.exists() else None
        try:
            router = loader.activate_capability_api_descriptor(descriptor)
            if router is None:
                continue
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
            routers.append(router)
            activated_capabilities.add(descriptor.capability_code)
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

    state["activated_capabilities"] = existing_activated | activated_capabilities
    return routers


def find_seeded_capability_for_path(app: FastAPI, path: str) -> Optional[str]:
    state = _get_runtime_state(app)
    for prefix, capability_code in state.get("sorted_prefix_entries", []):
        normalized = prefix.rstrip("/")
        if not normalized:
            continue
        if path == normalized or path.startswith(f"{normalized}/"):
            return capability_code
    return None


def activate_capability_api_code(
    *,
    app: FastAPI,
    capability_code: str,
    route_collector: Optional[List[Any]] = None,
    activation_mode: str = "request_activate",
    activation_service: Optional[Any] = None,
) -> List[APIRouter]:
    state = _get_runtime_state(app)
    activation_lock = state["activation_lock"]
    with activation_lock:
        if capability_code in state.get("activated_capabilities", set()):
            return []
        descriptors = state.get("descriptors_by_capability", {}).get(capability_code) or []
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
    Load and return all capability API routers

    Args:
        remote_capabilities_dir: Path to remote capabilities directory
        allowlist: Optional list of capability codes to load
        enable_all: If True, load all capabilities

    Returns:
        List of APIRouter instances
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
