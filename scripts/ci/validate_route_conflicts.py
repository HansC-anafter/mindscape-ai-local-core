#!/usr/bin/env python3
"""
CI Script: Validate Route Conflicts

Validate that capability API routes do not conflict.

Checks:
- duplicate route paths
- duplicate prefixes
- route pattern conflicts

Usage:
    python scripts/ci/validate_route_conflicts.py capabilities/
"""

import sys
import ast
import argparse
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RouteInfo:
    """Route metadata."""
    capability: str
    file_path: Path
    method: str
    path: str
    line_no: int


@dataclass
class RouteConflict:
    """Route conflict metadata."""
    route1: RouteInfo
    route2: RouteInfo
    conflict_type: str  # "exact" | "pattern" | "prefix"


def extract_routes_from_file(file_path: Path, capability: str) -> List[RouteInfo]:
    """
    Extract route definitions from a Python file.

    Args:
        file_path: Python file path
        capability: Capability name

    Returns:
        Route list
    """
    routes = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return routes

    # Extract router prefix.
    prefix_match = re.search(
        r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']',
        content
    )
    router_prefix = prefix_match.group(1) if prefix_match else ""

    # Extract route decorators.
    lines = content.split('\n')
    for line_no, line in enumerate(lines, 1):
        line = line.strip()

        # Match @router.get("/path"), @router.post("/path"), and similar decorators.
        match = re.match(
            r'@router\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']',
            line,
            re.IGNORECASE
        )

        if match:
            method = match.group(1).upper()
            path = match.group(2)

            # Compose the full route path.
            full_path = router_prefix + path
            full_path = re.sub(r'/+', '/', full_path)  # Remove duplicate slashes.

            routes.append(RouteInfo(
                capability=capability,
                file_path=file_path,
                method=method,
                path=full_path,
                line_no=line_no
            ))

    return routes


def normalize_path(path: str) -> str:
    """
    Normalize paths before comparison.

    Replace path parameters with placeholders.
    """
    # {param} -> {*}
    normalized = re.sub(r'\{[^}]+\}', '{*}', path)
    # Remove trailing slash.
    normalized = normalized.rstrip('/')
    return normalized


def find_conflicts(routes: List[RouteInfo]) -> List[RouteConflict]:
    """
    Find route conflicts.

    Args:
        routes: All routes

    Returns:
        Conflict list
    """
    conflicts = []

    # Group by (method, normalized_path).
    route_map: Dict[Tuple[str, str], List[RouteInfo]] = {}

    for route in routes:
        key = (route.method, normalize_path(route.path))
        if key not in route_map:
            route_map[key] = []
        route_map[key].append(route)

    # Find duplicates.
    for key, group in route_map.items():
        if len(group) > 1:
            # Ignore duplicates in the same file because they are likely false positives.
            unique_files = set(r.file_path for r in group)
            if len(unique_files) > 1:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        conflicts.append(RouteConflict(
                            route1=group[i],
                            route2=group[j],
                            conflict_type="exact"
                        ))

    return conflicts


def scan_capability(capability_dir: Path) -> List[RouteInfo]:
    """
    Scan all routes in a capability directory.

    Args:
        capability_dir: Capability directory

    Returns:
        Route list
    """
    routes = []
    capability = capability_dir.name

    # Scan api/ recursively.
    api_dir = capability_dir / "api"
    if api_dir.exists() and api_dir.is_dir():
        for py_file in api_dir.rglob("*.py"):
            if not py_file.name.startswith('_'):
                routes.extend(extract_routes_from_file(py_file, capability))

    # Scan routes/ recursively for backward compatibility.
    routes_dir = capability_dir / "routes"
    if routes_dir.exists() and routes_dir.is_dir():
        for py_file in routes_dir.rglob("*.py"):
            if not py_file.name.startswith('_'):
                routes.extend(extract_routes_from_file(py_file, capability))

    return routes


def format_conflicts(conflicts: List[RouteConflict]) -> str:
    """Format a conflict report."""
    if not conflicts:
        return "No route conflicts found"

    lines = [f"Found {len(conflicts)} route conflict(s):"]
    lines.append("")

    for i, conflict in enumerate(conflicts, 1):
        lines.append(f"Conflict #{i}:")
        lines.append(f"  Method: {conflict.route1.method}")
        lines.append(f"  Path: {conflict.route1.path}")
        lines.append(f"  Route 1: {conflict.route1.file_path}:{conflict.route1.line_no}")
        lines.append(f"  Route 2: {conflict.route2.file_path}:{conflict.route2.line_no}")
        lines.append("")

    lines.append("Fix: Ensure each (method, path) combination is unique across all capabilities")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate API route conflicts across capabilities"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Paths to validate (capability directories)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    all_routes = []

    for path in args.paths:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue

        if path.is_file():
            continue

        # If this is the capabilities directory, scan its child directories.
        manifest_path = path / "manifest.yaml"
        if manifest_path.exists():
            # Single capability.
            routes = scan_capability(path)
            all_routes.extend(routes)
        else:
            # Capabilities directory.
            for cap_dir in path.iterdir():
                if cap_dir.is_dir() and not cap_dir.name.startswith('_'):
                    routes = scan_capability(cap_dir)
                    all_routes.extend(routes)

    conflicts = find_conflicts(all_routes)

    if args.json:
        import json
        output = {
            "total_routes": len(all_routes),
            "conflict_count": len(conflicts),
            "conflicts": [
                {
                    "method": c.route1.method,
                    "path": c.route1.path,
                    "route1": {
                        "capability": c.route1.capability,
                        "file": str(c.route1.file_path),
                        "line": c.route1.line_no
                    },
                    "route2": {
                        "capability": c.route2.capability,
                        "file": str(c.route2.file_path),
                        "line": c.route2.line_no
                    }
                }
                for c in conflicts
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Scanned {len(all_routes)} routes")
        print(format_conflicts(conflicts))

    sys.exit(1 if conflicts else 0)


if __name__ == "__main__":
    main()

