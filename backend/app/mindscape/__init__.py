"""
Mindscape Environment Abstraction Layer

Provides unified import entry point, automatically handles path differences
between Cloud and Local-Core environments.
All capability code must use `from mindscape.capabilities.xxx import yyy`.
"""

import sys
import os
from pathlib import Path
from typing import Optional
import importlib
import importlib.util
import importlib.abc
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


def detect_environment() -> str:
    """
    Auto-detect current runtime environment.

    Priority order (highest to lowest):
    1. MINDSCAPE_ENVIRONMENT environment variable (explicit)
    2. MINDSCAPE_CAPABILITIES_ROOT environment variable (explicit root)
    3. /app/capabilities (Cloud container environment)
    4. /app/backend/app/capabilities (Local-Core container environment)
    5. capabilities/ in current directory (development, Cloud mode)
    6. backend/app/capabilities/ in current directory (development, Local-Core mode)

    Note: If multiple paths exist (e.g., some dev containers), priority order applies.
    Example: If both /app/capabilities and /app/backend/app/capabilities exist,
    Cloud detection takes precedence.

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


class AliasLoader(importlib.abc.Loader):
    """
    No-op loader for alias imports.

    Ensures import system correctly handles alias imports, avoiding toolchain side effects.
    """

    def __init__(self, real_module):
        self.real_module = real_module

    def create_module(self, spec):
        """Return the already-loaded real module."""
        return self.real_module

    def exec_module(self, module):
        """No-op: module already loaded, no execution needed."""
        return


class MindscapeImportFinder(importlib.abc.MetaPathFinder):
    """
    Custom import finder for mindscape.capabilities.* imports.

    Inherits importlib.abc.MetaPathFinder to comply with standard import mechanism,
    ensuring type checking/static analysis/import tools can correctly identify.

    Automatically maps mindscape.capabilities.xxx to:
    - Cloud: capabilities.xxx
    - Local-Core: backend.app.capabilities.xxx

    Uses alias import mechanism: directly loads real module and registers as virtual name.
    This approach is most robust and correctly handles packages and submodules.

    Important behavior:
    - sys.modules["mindscape.capabilities.xxx"] points to real module object
    - Real module's __name__ remains original (capabilities.xxx or backend.app.capabilities.xxx)
    - This is expected behavior for alias imports

    Impact:
    - trace/log/error messages show real module names (this is normal)
    - Tools relying on __name__/__spec__.name may show original names (expected)

    If tool compatibility issues arise, consider sys.path/namespace package mapping,
    but that requires directory structure changes and is not recommended for existing codebase.
    """

    def __init__(self, env: str):
        self.env = env
        self._path_mapping = {
            "cloud": "capabilities",
            "local-core": "backend.app.capabilities",
        }

    def _map_path(self, fullname: str) -> str:
        """Map mindscape.capabilities.xxx to environment-specific path"""
        # mindscape.capabilities.xxx -> capabilities.xxx (cloud)
        # mindscape.capabilities.xxx -> backend.app.capabilities.xxx (local-core)
        suffix = fullname.replace("mindscape.capabilities", "")
        base = self._path_mapping.get(self.env, "capabilities")
        return f"{base}{suffix}"

    def find_spec(self, fullname: str, path=None, target=None):
        """
        Modern import finder interface (Python 3.4+).

        Uses alias import: directly loads real module and registers in sys.modules as virtual name.
        This preserves all package information (submodule_search_locations, origin, etc.).

        Uses AliasLoader instead of loader=None to avoid toolchain side effects:
        - Ensures introspection tools work correctly
        - Ensures reload and namespace detection consistency
        - Ensures submodule resolution behavior consistency
        """
        if not fullname.startswith("mindscape.capabilities"):
            return None

        # If already loaded, return existing module
        if fullname in sys.modules:
            existing_module = sys.modules[fullname]

            spec = importlib.util.spec_from_loader(
                fullname,
                loader=AliasLoader(existing_module)
            )

            # Prefer existing_module.__spec__ package info (more robust)
            if hasattr(existing_module, '__spec__') and existing_module.__spec__:
                existing_spec = existing_module.__spec__
                if existing_spec.submodule_search_locations:
                    spec.submodule_search_locations = list(existing_spec.submodule_search_locations)
            else:
                # Fallback: if module has no spec, try to get from real path
                real_path = self._map_path(fullname)
                real_spec = importlib.util.find_spec(real_path)
                if real_spec and real_spec.submodule_search_locations:
                    spec.submodule_search_locations = list(real_spec.submodule_search_locations)

            return spec

        # Map to real path
        real_path = self._map_path(fullname)

        try:
            # Get real spec first (before loading)
            real_spec = importlib.util.find_spec(real_path)

            # Directly load real module (using alias import)
            real_module = importlib.import_module(real_path)

            # Register real module as virtual name (alias)
            # Note: real_module.__name__ remains original (capabilities.xxx), this is expected
            sys.modules[fullname] = real_module

            # Use AliasLoader instead of loader=None to avoid toolchain side effects
            spec = importlib.util.spec_from_loader(
                fullname,
                loader=AliasLoader(real_module)
            )

            # Important: copy package info to alias spec
            # This ensures submodule resolution works correctly (e.g., mindscape.capabilities.xxx.yyy)
            if real_spec and real_spec.submodule_search_locations:
                spec.submodule_search_locations = list(real_spec.submodule_search_locations)

            return spec
        except ImportError:
            # Real module doesn't exist, return None to let Python raise error
            return None


# Initialize environment abstraction layer
_current_env = detect_environment()
_import_finder = MindscapeImportFinder(_current_env)

# Register custom import finder (using modern interface)
if _import_finder not in sys.meta_path:
    sys.meta_path.insert(0, _import_finder)

logger.info(f"Mindscape environment abstraction initialized: env={_current_env}")


def get_environment(force_reload: bool = False, update_cache: bool = False) -> str:
    """
    Get current environment

    Args:
        force_reload: If True, re-detect environment instead of using cached value.
                     Use this when environment might have changed (e.g., in DI providers).
        update_cache: If True, update the cached _current_env and import finder.
                     Use this when you want to globally update the environment detection.

    Returns:
        Current environment string ("cloud" | "local-core" | "unknown")
    """
    if force_reload:
        # Re-detect environment (for DI providers and other dynamic detection scenarios)
        new_env = detect_environment()

        # If cache update requested, synchronously update _current_env and import finder
        if update_cache and new_env != _current_env:
            refresh_environment_cache(new_env)

        return new_env
    return _current_env


def refresh_environment_cache(new_env: Optional[str] = None) -> str:
    """
    Refresh environment cache and update import finder.

    Call this function to synchronously update when environment changes at runtime
    (e.g., tests, container restarts):
    - _current_env cache
    - MindscapeImportFinder environment configuration

    Args:
        new_env: New environment value. If None, re-detect.

    Returns:
        Updated environment value
    """
    global _current_env, _import_finder

    if new_env is None:
        new_env = detect_environment()

    if new_env != _current_env:
        _current_env = new_env
        # Update import finder environment configuration
        _import_finder.env = new_env
        logger.info(f"Environment cache refreshed: {_current_env}")

    return _current_env


def is_cloud_environment() -> bool:
    return get_environment() == "cloud"


def is_local_core_environment() -> bool:
    return get_environment() == "local-core"


def get_capabilities_base_path() -> Path:
    """Get base path for capabilities directory"""
    # Prefer explicitly specified root directory
    if CAPABILITIES_ROOT:
        root_path = Path(CAPABILITIES_ROOT)
        if root_path.exists():
            return root_path

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
