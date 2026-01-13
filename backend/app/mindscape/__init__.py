"""
Mindscape Environment Abstraction Layer

Provides environment detection utilities for Cloud and Local-Core deployments.
All capability code should use actual package names:
- Use: `from capabilities.xxx import yyy` or `from app.capabilities.xxx import yyy`
- Do NOT use: `from mindscape.capabilities.xxx import yyy` (removed, no longer supported)
"""

import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT: str = os.getenv("MINDSCAPE_ENVIRONMENT", "auto")
CAPABILITIES_ROOT: Optional[str] = os.getenv("MINDSCAPE_CAPABILITIES_ROOT")

__version__ = "1.0.0"
__all__ = [
    "get_environment",
    "refresh_environment_cache",
    "get_capabilities_base_path",
    "is_cloud_environment",
    "is_local_core_environment",
    "ENVIRONMENT",
]

# Global environment cache
_current_env: Optional[str] = None


def detect_environment() -> str:
    """
    Auto-detect current runtime environment.

    Priority order (highest to lowest):
    1. MINDSCAPE_ENVIRONMENT environment variable (explicit)
    2. MINDSCAPE_CAPABILITIES_ROOT environment variable (explicit root)
    3. /app/capabilities (Cloud deployment container environment)
    4. /app/backend/app/capabilities (Local-Core container environment)
    5. capabilities/ in current directory (development, Cloud deployment mode)
    6. backend/app/capabilities/ in current directory (development, Local-Core mode)

    Note: "cloud" here refers to the cloud deployment environment structure,
    detected based on directory paths, not a hardcoded assumption.

    Note: If multiple paths exist (e.g., some dev containers), priority order applies.
    Example: If both /app/capabilities and /app/backend/app/capabilities exist,
    Cloud deployment structure detection takes precedence.

    Returns:
        "cloud" | "local-core" | "unknown"
    """
    if ENVIRONMENT != "auto":
        return ENVIRONMENT

    if CAPABILITIES_ROOT:
        root_path = Path(CAPABILITIES_ROOT)
        if root_path.exists():
            if "backend" in str(root_path) and "app" in str(root_path):
                return "local-core"
            return "cloud"

    if Path("/app/capabilities").exists():
        return "cloud"
    if Path("/app/backend/app/capabilities").exists():
        return "local-core"

    cwd = Path.cwd()
    if (cwd / "capabilities").exists():
        return "cloud"
    if (cwd / "backend" / "app" / "capabilities").exists():
        return "local-core"

    # Try to infer from current file location (development environment)
    current_file_cap = Path(__file__).resolve().parent.parent / "capabilities"
    if current_file_cap.exists():
        return "local-core"

    return "unknown"


# Initialize environment cache
_current_env = detect_environment()
logger.info(f"Mindscape environment abstraction initialized: env={_current_env}")


def get_environment(force_reload: bool = False) -> str:
    """
    Get current environment

    Args:
        force_reload: If True, re-detect environment instead of using cached value.
                     Use this when environment might have changed (e.g., in DI providers).

    Returns:
        Current environment string ("cloud" | "local-core" | "unknown")
    """
    global _current_env
    if force_reload:
        _current_env = detect_environment()
    return _current_env


def refresh_environment_cache(new_env: Optional[str] = None) -> str:
    """
    Refresh environment cache.

    Call this function to synchronously update when environment changes at runtime
    (e.g., tests, container restarts).

    Args:
        new_env: New environment value. If None, re-detect.

    Returns:
        Updated environment value
    """
    global _current_env

    if new_env is None:
        new_env = detect_environment()

    if new_env != _current_env:
        _current_env = new_env
        logger.info(f"Environment cache refreshed: {_current_env}")

    return _current_env


def is_cloud_environment() -> bool:
    """Check if current environment is cloud deployment"""
    return get_environment() == "cloud"


def is_local_core_environment() -> bool:
    """Check if current environment is local-core deployment"""
    return get_environment() == "local-core"


def get_capabilities_base_path() -> Path:
    """Get base path for capabilities directory"""
    # Prefer explicitly specified root directory
    if CAPABILITIES_ROOT:
        root_path = Path(CAPABILITIES_ROOT)
        if root_path.exists():
            return root_path

    # Note: "cloud" here refers to cloud deployment environment structure,
    # detected based on directory paths, not a hardcoded assumption
    if _current_env == "cloud":
        return Path("/app/capabilities")
    elif _current_env == "local-core":
        return Path("/app/backend/app/capabilities")
    else:
        # Development mode
        cwd = Path.cwd()
        if (cwd / "capabilities").exists():
            return cwd / "capabilities"
        if (cwd / "backend" / "app" / "capabilities").exists():
            return cwd / "backend" / "app" / "capabilities"
        raise RuntimeError(
            "Cannot determine capabilities base path. "
            "Set MINDSCAPE_CAPABILITIES_ROOT environment variable to specify the path."
        )
