"""Semantic version utilities for baseline stale detection.

Implements SemVer parsing and comparison logic to determine if a baseline
is stale based on version changes (major/minor/patch).
"""

import re
from typing import Dict, Any, Literal, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SemVer:
    """Semantic version representation."""
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None
    build: Optional[str] = None

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version


def parse_semver(version: str) -> Optional[SemVer]:
    """
    Parse semantic version string.

    Supports formats:
    - "1.0.0"
    - "1.0.0-alpha"
    - "1.0.0-alpha+001"
    - "1.0.0+20130313144700"

    Returns None if version string is invalid.
    """
    if not version:
        return None

    # Basic SemVer pattern: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
    pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9\-\.]+))?(?:\+([a-zA-Z0-9\-\.]+))?$'
    match = re.match(pattern, version.strip())

    if not match:
        return None

    major, minor, patch, prerelease, build = match.groups()

    try:
        return SemVer(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            prerelease=prerelease if prerelease else None,
            build=build if build else None
        )
    except ValueError:
        return None


def compare_versions(old_version: Optional[str], new_version: Optional[str]) -> Dict[str, Any]:
    """
    Compare two semantic versions.

    Returns:
    {
        "level": "major" | "minor" | "patch" | "none",
        "is_newer": bool,
        "old_version": str,
        "new_version": str,
        "reason": str  # Human-readable reason
    }

    If either version is None or invalid, returns:
    {
        "level": "unknown",
        "is_newer": False,
        "old_version": old_version or "",
        "new_version": new_version or "",
        "reason": "Invalid version format"
    }
    """
    if not old_version or not new_version:
        return {
            "level": "unknown",
            "is_newer": False,
            "old_version": old_version or "",
            "new_version": new_version or "",
            "reason": "One or both versions are missing"
        }

    old_semver = parse_semver(old_version)
    new_semver = parse_semver(new_version)

    if not old_semver or not new_semver:
        return {
            "level": "unknown",
            "is_newer": False,
            "old_version": old_version,
            "new_version": new_version,
            "reason": "Invalid version format"
        }

    # Compare versions
    if new_semver.major > old_semver.major:
        return {
            "level": "major",
            "is_newer": True,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"MAJOR version change: {old_version} → {new_version} (breaking changes)"
        }
    elif new_semver.major < old_semver.major:
        return {
            "level": "major",
            "is_newer": False,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"MAJOR version downgrade: {old_version} → {new_version}"
        }

    if new_semver.minor > old_semver.minor:
        return {
            "level": "minor",
            "is_newer": True,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"MINOR version change: {old_version} → {new_version} (new features)"
        }
    elif new_semver.minor < old_semver.minor:
        return {
            "level": "minor",
            "is_newer": False,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"MINOR version downgrade: {old_version} → {new_version}"
        }

    if new_semver.patch > old_semver.patch:
        return {
            "level": "patch",
            "is_newer": True,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"PATCH version change: {old_version} → {new_version} (bug fixes)"
        }
    elif new_semver.patch < old_semver.patch:
        return {
            "level": "patch",
            "is_newer": False,
            "old_version": old_version,
            "new_version": new_version,
            "reason": f"PATCH version downgrade: {old_version} → {new_version}"
        }

    # Versions are equal
    return {
        "level": "none",
        "is_newer": False,
        "old_version": old_version,
        "new_version": new_version,
        "reason": f"Versions are equal: {old_version}"
    }


def bump_version(
    current_version: str,
    change_type: Literal["major", "minor", "patch"]
) -> str:
    """
    Bump semantic version based on change type.

    Args:
        current_version: Current version string (e.g., "1.0.0")
        change_type: Type of change ("major", "minor", "patch")

    Returns:
        New version string

    Raises:
        ValueError: If current_version is invalid or change_type is unknown
    """
    semver = parse_semver(current_version)
    if not semver:
        raise ValueError(f"Invalid version format: {current_version}")

    if change_type == "major":
        return str(SemVer(
            major=semver.major + 1,
            minor=0,
            patch=0,
            prerelease=semver.prerelease,
            build=semver.build
        ))
    elif change_type == "minor":
        return str(SemVer(
            major=semver.major,
            minor=semver.minor + 1,
            patch=0,
            prerelease=semver.prerelease,
            build=semver.build
        ))
    elif change_type == "patch":
        return str(SemVer(
            major=semver.major,
            minor=semver.minor,
            patch=semver.patch + 1,
            prerelease=semver.prerelease,
            build=semver.build
        ))
    else:
        raise ValueError(f"Unknown change_type: {change_type}")
