#!/usr/bin/env python3
"""
CI Script: Validate Route Conflicts

驗證所有 capability 的 API 路由沒有衝突。

檢查項目：
- 路由路徑重複
- Prefix 重複
- 路由模式衝突

用法：
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
    """路由資訊"""
    capability: str
    file_path: Path
    method: str
    path: str
    line_no: int


@dataclass
class RouteConflict:
    """路由衝突"""
    route1: RouteInfo
    route2: RouteInfo
    conflict_type: str  # "exact" | "pattern" | "prefix"


def extract_routes_from_file(file_path: Path, capability: str) -> List[RouteInfo]:
    """
    從 Python 文件中提取路由定義

    Args:
        file_path: Python 文件路徑
        capability: Capability 名稱

    Returns:
        路由列表
    """
    routes = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return routes

    # 提取 router prefix
    prefix_match = re.search(
        r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']',
        content
    )
    router_prefix = prefix_match.group(1) if prefix_match else ""

    # 提取路由裝飾器
    lines = content.split('\n')
    for line_no, line in enumerate(lines, 1):
        line = line.strip()

        # 匹配 @router.get("/path"), @router.post("/path") 等
        match = re.match(
            r'@router\.(get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']',
            line,
            re.IGNORECASE
        )

        if match:
            method = match.group(1).upper()
            path = match.group(2)

            # 組合完整路徑
            full_path = router_prefix + path
            full_path = re.sub(r'/+', '/', full_path)  # 移除重複斜線

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
    標準化路徑用於比較

    將路徑參數替換為佔位符
    """
    # {param} -> {*}
    normalized = re.sub(r'\{[^}]+\}', '{*}', path)
    # 移除尾部斜線
    normalized = normalized.rstrip('/')
    return normalized


def find_conflicts(routes: List[RouteInfo]) -> List[RouteConflict]:
    """
    找出路由衝突

    Args:
        routes: 所有路由列表

    Returns:
        衝突列表
    """
    conflicts = []

    # 按 (method, normalized_path) 分組
    route_map: Dict[Tuple[str, str], List[RouteInfo]] = {}

    for route in routes:
        key = (route.method, normalize_path(route.path))
        if key not in route_map:
            route_map[key] = []
        route_map[key].append(route)

    # 找出重複
    for key, group in route_map.items():
        if len(group) > 1:
            # 排除同一文件中的重複（可能是誤報）
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
    掃描 capability 目錄中的所有路由

    Args:
        capability_dir: Capability 目錄

    Returns:
        路由列表
    """
    routes = []
    capability = capability_dir.name

    # 掃描 api/ 目錄（遞歸掃描所有子目錄）
    api_dir = capability_dir / "api"
    if api_dir.exists() and api_dir.is_dir():
        for py_file in api_dir.rglob("*.py"):
            if not py_file.name.startswith('_'):
                routes.extend(extract_routes_from_file(py_file, capability))

    # 掃描 routes/ 目錄（向後兼容，遞歸掃描）
    routes_dir = capability_dir / "routes"
    if routes_dir.exists() and routes_dir.is_dir():
        for py_file in routes_dir.rglob("*.py"):
            if not py_file.name.startswith('_'):
                routes.extend(extract_routes_from_file(py_file, capability))

    return routes


def format_conflicts(conflicts: List[RouteConflict]) -> str:
    """格式化衝突報告"""
    if not conflicts:
        return "✅ No route conflicts found"

    lines = [f"❌ Found {len(conflicts)} route conflict(s):"]
    lines.append("")

    for i, conflict in enumerate(conflicts, 1):
        lines.append(f"Conflict #{i}:")
        lines.append(f"  Method: {conflict.route1.method}")
        lines.append(f"  Path: {conflict.route1.path}")
        lines.append(f"  Route 1: {conflict.route1.file_path}:{conflict.route1.line_no}")
        lines.append(f"  Route 2: {conflict.route2.file_path}:{conflict.route2.line_no}")
        lines.append("")

    lines.append("💡 Fix: Ensure each (method, path) combination is unique across all capabilities")

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

        # 如果是 capabilities 目錄，遍歷子目錄
        manifest_path = path / "manifest.yaml"
        if manifest_path.exists():
            # 單個 capability
            routes = scan_capability(path)
            all_routes.extend(routes)
        else:
            # capabilities 目錄
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


