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

import yaml
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import logging
import os
from fastapi import APIRouter
from starlette.routing import Route, Mount

logger = logging.getLogger(__name__)


class CapabilityAPILoader:
    """Loads and registers API routers from cloud capability manifests"""

    def __init__(
        self,
        remote_capabilities_dir: Optional[Path] = None,
        allowlist: Optional[List[str]] = None,
        enable_all: bool = False
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
        self.loaded_routers: List[Tuple[APIRouter, str, Dict]] = []
        self.registered_routes: Set[Tuple[str, str]] = set()

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
                logger.warning(f"Env MINDSCAPE_REMOTE_CAPABILITIES_DIR points to non-existent path: {env_dir}")

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
        Load capabilities section from manifest.yaml

        Returns:
            List of capability definitions from manifest
        """
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = yaml.safe_load(f)

            capabilities = manifest.get('capabilities', [])
            if not isinstance(capabilities, list):
                return []

            return capabilities
        except Exception as e:
            logger.warning(f"Failed to load manifest from {manifest_path}: {e}")
            return []

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

        enabled_by_default = cap_def.get('enabled_by_default', True)
        return enabled_by_default

    def load_api_router_from_capability_def(
        self,
        capability_code: str,
        capability_dir: Path,
        cap_def: Dict
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
        api_path = cap_def.get('path')
        if not api_path:
            logger.warning(
                f"Capability {cap_def.get('code', 'unknown')} in {capability_code} "
                "has no path defined"
            )
            return None

        api_file_path = capability_dir / api_path
        if not api_file_path.exists():
            logger.warning(
                f"API file not found for {capability_code}: {api_file_path}"
            )
            return None

        capabilities_parent = capability_dir.parent
        if str(capabilities_parent) not in sys.path:
            sys.path.insert(0, str(capabilities_parent))

        # Also add cloud root (parent of capabilities) for imports like 'capabilities.xxx' and 'services.xxx'
        cloud_root = capabilities_parent.parent
        if str(cloud_root) not in sys.path:
            sys.path.insert(0, str(cloud_root))

        try:
            relative_path = api_file_path.relative_to(capabilities_parent)
            module_parts = list(relative_path.parts[:-1])
            module_name_base = '.'.join(module_parts)
            file_stem = api_file_path.stem
            module_name = f"{module_name_base}.{file_stem}"

            # Create module spec with proper package name to support relative imports
            # Use full package path like 'capabilities.brand_identity.api.cis_mapper_endpoints'
            spec = importlib.util.spec_from_file_location(module_name, api_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create module spec for {api_file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            # Set __package__ to support relative imports in imported modules
            if not hasattr(module, '__package__') or module.__package__ is None:
                # Extract package name from module_name (e.g., 'capabilities.brand_identity.api.cis_mapper_endpoints' -> 'capabilities.brand_identity.api')
                if '.' in module_name:
                    module.__package__ = '.'.join(module_name.split('.')[:-1])
            spec.loader.exec_module(module)

            router_export = cap_def.get('router_export', 'router')

            if router_export == 'get_router':
                get_router_func = getattr(module, 'get_router', None)
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
            elif router_export == 'router':
                router = getattr(module, 'router', None)
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
                f"Failed to load API router from {api_file_path}: {e}",
                exc_info=True
            )
            return None

    def extract_routes_from_router(self, router: APIRouter) -> Set[Tuple[str, str]]:
        """
        Extract all (method, path) tuples from a router

        Args:
            router: APIRouter instance

        Returns:
            Set of (method, path) tuples
        """
        routes = set()

        def extract_from_route(route: Route, prefix: str = ""):
            methods = getattr(route, 'methods', set())
            path = prefix + route.path
            for method in methods:
                if method != 'HEAD':
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

        router_prefix = getattr(router, 'prefix', '') or ''

        for route in router.routes:
            if isinstance(route, Route):
                extract_from_route(route, router_prefix)
            elif isinstance(route, Mount):
                extract_from_mount(route, router_prefix)
            elif isinstance(route, APIRouter):
                nested_prefix = getattr(route, 'prefix', '') or ''
                full_prefix = router_prefix + nested_prefix
                for nested_route in route.routes:
                    if isinstance(nested_route, Route):
                        extract_from_route(nested_route, full_prefix)
                    elif isinstance(nested_route, Mount):
                        extract_from_mount(nested_route, full_prefix)

        return routes

    def check_route_conflicts(
        self,
        router: APIRouter,
        capability_code: str,
        cap_def: Dict
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
        new_routes = self.extract_routes_from_router(router)
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
        capabilities_dir = self.find_remote_capabilities_dir()
        if not capabilities_dir:
            logger.warning(
                "Remote capabilities directory not found. "
                "Skipping capability API loading."
            )
            return []

        if not capabilities_dir.exists():
            logger.warning(f"Remote capabilities directory does not exist: {capabilities_dir}")
            return []

        loaded_routers = []

        # Scan each capability directory
        for capability_dir in capabilities_dir.iterdir():
            if not capability_dir.is_dir() or capability_dir.name.startswith('_'):
                continue

            capability_code = capability_dir.name

            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.debug(f"No manifest.yaml found in {capability_dir}, skipping")
                continue

            # Load capabilities from manifest
            capabilities = self.load_manifest_capabilities(manifest_path)
            if not capabilities:
                logger.debug(f"No capabilities defined in manifest for {capability_code}")
                continue

            # Load each API router
            for cap_def in capabilities:
                if not isinstance(cap_def, dict):
                    continue

                # Check if should load this capability
                if not self.should_load_capability(capability_code, cap_def):
                    logger.debug(
                        f"Skipping {capability_code} (not in allowlist and enabled_by_default=False)"
                    )
                    continue

                router = self.load_api_router_from_capability_def(
                    capability_code,
                    capability_dir,
                    cap_def
                )

                if router:
                    is_valid, conflicts = self.check_route_conflicts(router, capability_code, cap_def)
                    if is_valid:
                        loaded_routers.append(router)
                        self.loaded_routers.append((router, capability_code, cap_def))

                    else:
                        conflict_details = ", ".join([f"{m} {p}" for m, p in conflicts])
                        raise ValueError(
                            f"Route conflict detected for capability {capability_code}: "
                            f"Routes {conflict_details} are already registered. "
                            f"Please check router prefix and path definitions."
                        )

        logger.info(
            f"Loaded {len(loaded_routers)} API routers from cloud capabilities"
        )
        return loaded_routers


def load_capability_apis(
    remote_capabilities_dir: Optional[Path] = None,
    allowlist: Optional[List[str]] = None,
    enable_all: bool = False
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
    loader = CapabilityAPILoader(remote_capabilities_dir, allowlist, enable_all)
    return loader.load_all_capability_apis()
