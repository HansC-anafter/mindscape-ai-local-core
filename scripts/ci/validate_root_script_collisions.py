#!/usr/bin/env python3
"""
Block repo-root script files that break the cloud/local-core script boundary.

Why:
- Capability-owned runtime helpers belong under backend/app/capabilities/<cap>/scripts/.
- Capability-specific development helpers do not belong under repo-root scripts/.
- Repo-root scripts/ is reserved for core host tooling, startup, install, CI, and
  generic runtime maintenance.
"""

from __future__ import annotations

import sys
from pathlib import Path

IGNORED_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}
IGNORED_FILE_NAMES = {".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
BOUNDARY_SCAN_SUFFIXES = {".py", ".sh", ".ps1", ".bat"}
FORBIDDEN_NAME_FRAGMENTS = (
    "obsidian",
    "instagram",
    "ig_",
    "performance_direction",
    "practice_companion",
    "public_persona",
    "multi_media_studio",
    "semantic_seeds",
    "layer_asset_forge",
    "video_renderer",
    "blender_bridge",
    "spatial_demo",
)
FORBIDDEN_CONTENT_PATTERNS = (
    "from capabilities.",
    "import capabilities.",
    "obsidian_vault_organize",
    "ig_post_generation",
    "instagram.com/",
    "/app/data/ig-browser-profiles",
)


def iter_script_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIR_NAMES for part in relative.parts[:-1]):
            continue
        if path.name in IGNORED_FILE_NAMES:
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        yield path


def find_collisions(repo_root: Path) -> list[tuple[Path, str, Path]]:
    root_scripts_dir = repo_root / "scripts"
    capabilities_root = repo_root / "backend" / "app" / "capabilities"
    if not root_scripts_dir.exists() or not capabilities_root.exists():
        return []

    root_scripts_by_name: dict[str, list[Path]] = {}
    for script_path in iter_script_files(root_scripts_dir):
        root_scripts_by_name.setdefault(script_path.name, []).append(script_path)

    collisions: list[tuple[Path, str, Path]] = []
    for cap_scripts_dir in sorted(capabilities_root.glob("*/scripts")):
        capability_code = cap_scripts_dir.parent.name
        for cap_script in iter_script_files(cap_scripts_dir):
            for root_script in root_scripts_by_name.get(cap_script.name, []):
                collisions.append((root_script, capability_code, cap_script))
    return collisions


def find_boundary_violations(repo_root: Path) -> list[tuple[Path, str]]:
    root_scripts_dir = repo_root / "scripts"
    if not root_scripts_dir.exists():
        return []

    violations: list[tuple[Path, str]] = []
    for script_path in iter_script_files(root_scripts_dir):
        relative = script_path.relative_to(root_scripts_dir)
        if relative.parts and relative.parts[0] in {"ci", "git-hooks", "modules", "config", "mlx-server"}:
            continue
        if script_path.suffix not in BOUNDARY_SCAN_SUFFIXES:
            continue

        lower_name = script_path.name.lower()
        for fragment in FORBIDDEN_NAME_FRAGMENTS:
            if fragment in lower_name:
                violations.append((script_path, f"filename contains forbidden fragment '{fragment}'"))
                break
        else:
            content = script_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_CONTENT_PATTERNS:
                if pattern in content:
                    violations.append((script_path, f"content contains forbidden pattern '{pattern}'"))
                    break
    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    collisions = find_collisions(repo_root)
    boundary_violations = find_boundary_violations(repo_root)
    if not collisions and not boundary_violations:
        print("OK: repo-root scripts respect collision and boundary checks")
        return 0

    if collisions:
        print("ERROR: repo-root scripts collide with installed capability scripts:")
        for root_script, capability_code, cap_script in collisions:
            print(
                f"  - {root_script.relative_to(repo_root)} "
                f"duplicates {capability_code}::{cap_script.relative_to(repo_root)}"
            )
        print("Move capability-owned helpers back under backend/app/capabilities/<cap>/scripts/.")

    if boundary_violations:
        print("ERROR: repo-root scripts contain capability- or demo-specific helpers:")
        for script_path, reason in boundary_violations:
            print(f"  - {script_path.relative_to(repo_root)}: {reason}")
        print("Move pack/demo-specific helpers out of repo-root scripts/ and into internal archive or cloud canonical source.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
