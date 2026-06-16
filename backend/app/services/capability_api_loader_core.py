"""
Core descriptor discovery and router import logic for capability APIs.
"""

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from fastapi import APIRouter
from starlette.routing import Mount, Route

from .capability_api_loader_types import CapabilityAPIDescriptor
from .runtime_pack_hygiene import is_ignored_runtime_pack_dir

logger = logging.getLogger(__name__)


class CapabilityAPILoader:
    """Loads and registers API routers from installed capability manifests."""

    def __init__(
        self,
        remote_capabilities_dir: Optional[Path] = None,
        allowlist: Optional[List[str]] = None,
        enable_all: bool = False,
        installed_packs_store: Optional[Any] = None,
    ):
        """
        Initialize the API loader.

        Args:
            remote_capabilities_dir: Explicit capabilities directory override.
                This is retained for compatibility and tests; runtime discovery
                only scans local installed capability directories.
            allowlist: Optional list of capability codes to load.
                If None and enable_all=False, only enabled_by_default=True are loaded.
            enable_all: If True, load all capabilities regardless of allowlist/enabled_by_default.
        """
        self.capabilities_dir_override = remote_capabilities_dir
        self.remote_capabilities_dir = remote_capabilities_dir
        self.allowlist = set(allowlist) if allowlist else None
        self.enable_all = enable_all or os.getenv("ENABLE_ALL_CAPABILITIES") == "1"
        self.installed_packs_store = installed_packs_store
        self.loaded_routers: List[Tuple[APIRouter, str, Dict]] = []
        self.registered_routes: Set[Tuple[str, str]] = set()
        self._installed_pack_enablement: Optional[Dict[str, bool]] = None

    def _capabilities_dir_candidates(self) -> List[Tuple[str, Path]]:
        """Return installed-runtime capability directories in search order."""
        repo_local_capabilities_dir = (
            Path(__file__).resolve().parent.parent / "capabilities"
        )
        container_capabilities_dir = Path("/app/backend/app/capabilities")

        candidates: List[Tuple[str, Path]] = []
        if self.capabilities_dir_override is not None:
            candidates.append(("explicit override", self.capabilities_dir_override))
        candidates.extend(
            [
                ("repo-local installed", repo_local_capabilities_dir),
                ("container installed", container_capabilities_dir),
            ]
        )

        deduped: List[Tuple[str, Path]] = []
        seen: Set[str] = set()
        for label, path in candidates:
            path_key = str(path)
            if path_key in seen:
                continue
            seen.add(path_key)
            deduped.append((label, path))
        return deduped

    def load_manifest_capabilities(self, manifest_path: Path) -> List[Dict]:
        """
        Load APIs section from manifest.yaml.

        Returns:
            List of API definitions from manifest.
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
        1. explicit compatibility/test override
        2. local installed capabilities
        """
        for label, capabilities_dir in self._capabilities_dir_candidates():
            if capabilities_dir.exists():
                logger.info(
                    "Using %s capabilities directory: %s", label, capabilities_dir
                )
                return capabilities_dir
            if label == "explicit override":
                logger.warning(
                    "Capability API discovery override does not exist: %s",
                    capabilities_dir,
                )

        logger.warning(
            "No installed capabilities directory found. Skipping capability API loading."
        )
        return None

    def should_load_capability(self, capability_code: str, cap_def: Dict) -> bool:
        """
        Determine if a capability should be loaded based on allowlist and enabled_by_default.
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
            logger.warning(
                "Failed to load manifest document from %s: %s", manifest_path, exc
            )
        return {"code": manifest_path.parent.name}

    def _get_installed_pack_enabled(self, capability_code: str) -> Optional[bool]:
        if self._installed_pack_enablement is None:
            self._installed_pack_enablement = self._load_installed_pack_enablement()
        return self._installed_pack_enablement.get(capability_code)

    def _load_installed_pack_enablement(self) -> Dict[str, bool]:
        try:
            if self.installed_packs_store is None:
                from app.services.stores.installed_packs_store import (
                    InstalledPacksStore,
                )

                self.installed_packs_store = InstalledPacksStore()
            rows = self.installed_packs_store.list_installed_metadata()
            return {
                row["pack_id"]: bool(row.get("enabled"))
                for row in rows
                if row.get("pack_id")
            }
        except Exception as exc:
            logger.debug(
                "Installed pack enablement unavailable; falling back to manifests: %s",
                exc,
            )
            return {}

    def load_api_router_from_capability_def(
        self, capability_code: str, capability_dir: Path, cap_def: Dict
    ) -> Optional[APIRouter]:
        """
        Load API router from capability definition using router_export contract.
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

            spec = importlib.util.spec_from_file_location(module_name, api_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create module spec for {api_file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            if "." in module_name:
                module.__package__ = ".".join(module_name.split(".")[:-1])
            module.__file__ = str(api_file_path)
            if str(capability_dir) not in sys.path:
                sys.path.insert(0, str(capability_dir))
            previous_module = sys.modules.get(module_name)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                if previous_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = previous_module
                raise

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
        """Discover capability API descriptors from manifests without importing modules."""
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
            "Discovered %d capability API descriptor(s) from manifests",
            len(descriptors),
        )
        return descriptors

    def activate_capability_api_descriptor(
        self, descriptor: CapabilityAPIDescriptor
    ) -> Optional[APIRouter]:
        """Import and validate a capability API router from a discovered descriptor."""
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
        """Extract all (method, path) tuples from a router."""
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

        base_prefix = manifest_prefix

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
        """Check if router routes conflict with already registered routes."""
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
        Load all API routers from installed capabilities.

        Returns:
            List of APIRouter instances.
        """
        descriptors = self.discover_capability_api_descriptors()
        if not descriptors:
            return []

        loaded_routers = []
        for descriptor in descriptors:
            router = self.activate_capability_api_descriptor(descriptor)
            if router:
                loaded_routers.append(router)

        logger.info(
            "Loaded %d API routers from installed capabilities", len(loaded_routers)
        )
        return loaded_routers


def discover_capability_api_descriptors(
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False,
) -> List[CapabilityAPIDescriptor]:
    """Discover capability API descriptors without importing modules."""
    loader = CapabilityAPILoader(remote_capabilities_dir, allowlist, enable_all)
    return loader.discover_capability_api_descriptors()


__all__ = ["CapabilityAPILoader", "discover_capability_api_descriptors"]
