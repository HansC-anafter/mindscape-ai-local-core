"""
Route validator for capability API routes.

Validates that all routes declared in manifest are actually registered in FastAPI app.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from fastapi import FastAPI
from starlette.routing import Route, Mount

logger = logging.getLogger(__name__)


def extract_routes_from_app(app: FastAPI) -> Set[Tuple[str, str]]:
    """
    Extract all (method, path) tuples from FastAPI app

    Args:
        app: FastAPI application instance

    Returns:
        Set of (method, path) tuples
    """
    routes = set()

    def normalize_path(path: str) -> str:
        """Normalize path for comparison."""
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return path

    def extract_from_route(route: Route, prefix: str = ""):
        """Extract routes from a Route object"""
        methods = getattr(route, 'methods', set())
        path = normalize_path(prefix + route.path)
        for method in methods:
            if method != 'HEAD':
                routes.add((method.upper(), path))

    def extract_from_mount(mount: Mount, prefix: str = ""):
        """Extract routes from a Mount object"""
        mount_path = normalize_path(prefix + mount.path)
        for route in mount.routes:
            if isinstance(route, Route):
                extract_from_route(route, mount_path)
            elif isinstance(route, Mount):
                extract_from_mount(route, mount_path)
            elif isinstance(route, type(app.routes[0])):
                nested_prefix = getattr(route, 'prefix', '') or ''
                full_prefix = mount_path + nested_prefix
                for nested_route in route.routes:
                    if isinstance(nested_route, Route):
                        extract_from_route(nested_route, full_prefix)
                    elif isinstance(nested_route, Mount):
                        extract_from_mount(nested_route, full_prefix)

    for route in app.routes:
        if isinstance(route, Route):
            extract_from_route(route)
        elif isinstance(route, Mount):
            extract_from_mount(route)
        elif hasattr(route, 'routes'):
            router_prefix = getattr(route, 'prefix', '') or ''
            for sub_route in route.routes:
                if isinstance(sub_route, Route):
                    extract_from_route(sub_route, router_prefix)
                elif isinstance(sub_route, Mount):
                    extract_from_mount(sub_route, router_prefix)

    return routes


def parse_manifest_endpoint(endpoint_str: str) -> Tuple[str, str]:
    """
    Parse endpoint string from manifest (e.g., "GET /api/v1/workspaces/{workspace_id}/web-generation/baseline")

    Args:
        endpoint_str: Endpoint declaration string

    Returns:
        (method, path) tuple
    """
    parts = endpoint_str.strip().split(None, 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid endpoint format: {endpoint_str}. Expected 'METHOD /path'")
    method = parts[0].upper()
    path = parts[1]
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return (method, path)


def load_manifest_endpoints(
    remote_capabilities_dir: Path,
    capability_code: str
) -> List[Tuple[str, str]]:
    """
    Load declared endpoints from manifest

    Args:
        remote_capabilities_dir: Path to remote capabilities directory
        capability_code: Capability code

    Returns:
        List of (method, path) tuples
    """
    manifest_path = remote_capabilities_dir / capability_code / "manifest.yaml"
    if not manifest_path.exists():
        logger.warning(f"Manifest not found: {manifest_path}")
        return []

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)

        capabilities = manifest.get('capabilities', [])
        if not isinstance(capabilities, list):
            return []

        endpoints = []
        for cap_def in capabilities:
            if not isinstance(cap_def, dict):
                continue

            declared_endpoints = cap_def.get('endpoints', [])
            if not isinstance(declared_endpoints, list):
                continue

            for endpoint_str in declared_endpoints:
                try:
                    method, path = parse_manifest_endpoint(endpoint_str)
                    endpoints.append((method, path))
                except ValueError as e:
                    logger.warning(f"Failed to parse endpoint '{endpoint_str}': {e}")

        return endpoints

    except Exception as e:
        logger.error(f"Failed to load manifest from {manifest_path}: {e}", exc_info=True)
        return []


def validate_routes_against_manifest(
    app: FastAPI,
    remote_capabilities_dir: Optional[Path] = None,
    capability_codes: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Validate that all routes declared in manifest are actually registered in app

    Args:
        app: FastAPI application instance
        remote_capabilities_dir: Path to remote capabilities directory (optional)
        capability_codes: List of capability codes to validate (optional, validates all if None)

    Returns:
        (is_valid, error_messages) tuple
    """
    if remote_capabilities_dir is None:
        import os
        env_dir = os.getenv("MINDSCAPE_REMOTE_CAPABILITIES_DIR")
        if env_dir:
            remote_capabilities_dir = Path(env_dir)
        else:
            remote_capabilities_dir = None

    if not remote_capabilities_dir or not remote_capabilities_dir.exists():
        import os
        skip_validation = os.getenv("SKIP_ROUTE_VALIDATION") == "1"
        
        # In local-core, route validation is optional (cloud capabilities not required)
        # Skip validation if MINDSCAPE_REMOTE_CAPABILITIES_DIR is not set or SKIP_ROUTE_VALIDATION=1
        if not remote_capabilities_dir or skip_validation:
            logger.info(
                "Remote capabilities directory not configured. "
                "Skipping route validation (this is normal for local-core deployments)."
            )
            return True, []
        
        # Only raise error if directory was explicitly set but doesn't exist
        error_msg = (
            f"Remote capabilities directory not found: {remote_capabilities_dir}. "
            f"Cannot validate routes. Please set MINDSCAPE_REMOTE_CAPABILITIES_DIR environment variable "
            f"or set SKIP_ROUTE_VALIDATION=1 to skip validation."
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    actual_routes = extract_routes_from_app(app)

    if capability_codes is None:
        capability_codes = [
            d.name for d in remote_capabilities_dir.iterdir()
            if d.is_dir() and not d.name.startswith('_') and (d / "manifest.yaml").exists()
        ]

    errors = []
    for capability_code in capability_codes:
        declared_endpoints = load_manifest_endpoints(remote_capabilities_dir, capability_code)
        if not declared_endpoints:
            logger.debug(f"No endpoints declared in manifest for {capability_code}")
            continue

        for method, path in declared_endpoints:
            if (method, path) not in actual_routes:
                error_msg = (
                    f"Route mismatch for {capability_code}: "
                    f"Manifest declares {method} {path} but route is not registered in app"
                )
                errors.append(error_msg)
                logger.error(error_msg)

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_on_startup(app: FastAPI) -> None:
    """
    Validate routes on startup.

    Should be called after all routers are registered.

    Args:
        app: FastAPI application instance

    Raises:
        RuntimeError: If routes declared in manifest are not registered (only if SKIP_ROUTE_VALIDATION is not set)
        FileNotFoundError: If cloud capabilities directory not found
    """
    import os

    # Check if route validation should be skipped
    skip_validation = os.getenv("SKIP_ROUTE_VALIDATION") == "1"

    is_valid, errors = validate_routes_against_manifest(app)
    if not is_valid:
        error_summary = "\n".join(f"  - {e}" for e in errors)
        error_message = (
            f"Route validation failed. The following routes declared in manifests "
            f"are not registered in the app:\n{error_summary}\n\n"
            f"This indicates a mismatch between manifest declarations and actual route registration. "
            f"Please check that capability API loaders are working correctly."
        )

        if skip_validation:
            logger.warning(f"{error_message}\n(Skipping validation due to SKIP_ROUTE_VALIDATION=1)")
            return
        else:
            raise RuntimeError(error_message)
    logger.info("Route validation passed: all manifest-declared routes are registered")
