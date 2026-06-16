"""Package and import parent helpers for playbook tool validation."""

import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(f"{__package__}.tool_validation")


def _discover_capability_dir(
    capabilities_dir: Path, capability_code: str
) -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Resolve the installed capability directory and its import roots."""
    possible_dir_names = [
        capability_code,
        capability_code.replace("_", "-"),
        capability_code.replace("-", "_"),
    ]
    capability_dir = None
    for dir_name in possible_dir_names:
        candidate_dir = capabilities_dir / dir_name
        if candidate_dir.exists():
            capability_dir = candidate_dir
            break

    if capability_dir is None:
        return None, None, None

    capabilities_parent = capability_dir.parent
    cloud_root = capabilities_parent.parent
    backend_root = cloud_root.parent

    for path in [capabilities_parent, cloud_root, backend_root]:
        if path and str(path) not in sys.path:
            sys.path.insert(0, str(path))

    return capability_dir, cloud_root, backend_root


def _ensure_capabilities_package(
    capabilities_dir: Path, capability_dir: Path, capability_code: str
) -> str:
    """Ensure `capabilities.<capability_code>` is importable."""
    capabilities_parent = capability_dir.parent
    if "capabilities" not in sys.modules:
        capabilities_module = types.ModuleType("capabilities")
        capabilities_module.__path__ = [str(capabilities_parent)]
        sys.modules["capabilities"] = capabilities_module

    cap_module_path = f"capabilities.{capability_code}"
    if cap_module_path not in sys.modules:
        cap_module = types.ModuleType(cap_module_path)
        cap_module.__path__ = [str(capability_dir)]
        sys.modules[cap_module_path] = cap_module
        setattr(sys.modules["capabilities"], capability_code, cap_module)

    app_capabilities_path = "app.capabilities"
    if "app" not in sys.modules:
        try:
            importlib.import_module("app")
        except Exception:
            app_module = types.ModuleType("app")
            app_module.__path__ = [str(capabilities_parent.parent)]
            init_file = capabilities_parent.parent / "__init__.py"
            if init_file.exists():
                spec = importlib.util.spec_from_file_location(
                    "app",
                    init_file,
                    submodule_search_locations=[str(capabilities_parent.parent)],
                )
                if spec:
                    app_module.__spec__ = spec
            sys.modules["app"] = app_module

    if app_capabilities_path not in sys.modules:
        app_capabilities_module = types.ModuleType(app_capabilities_path)
        app_capabilities_module.__path__ = [str(capabilities_dir)]
        capabilities_init = capabilities_dir / "__init__.py"
        if not capabilities_init.exists():
            capabilities_init.touch()
        if capabilities_init.exists():
            spec = importlib.util.spec_from_file_location(
                app_capabilities_path,
                capabilities_init,
                submodule_search_locations=[str(capabilities_dir)],
            )
            if spec:
                app_capabilities_module.__spec__ = spec
        sys.modules[app_capabilities_path] = app_capabilities_module
        if not hasattr(sys.modules["app"], "capabilities"):
            setattr(sys.modules["app"], "capabilities", app_capabilities_module)

    app_cap_module_path = f"app.capabilities.{capability_code}"
    if app_cap_module_path not in sys.modules:
        app_cap_module = types.ModuleType(app_cap_module_path)
        app_cap_module.__path__ = [str(capability_dir)]
        init_file = capability_dir / "__init__.py"
        if init_file.exists():
            spec = importlib.util.spec_from_file_location(
                app_cap_module_path,
                init_file,
                submodule_search_locations=[str(capability_dir)],
            )
            if spec:
                app_cap_module.__spec__ = spec
        sys.modules[app_cap_module_path] = app_cap_module
        setattr(sys.modules[app_capabilities_path], capability_code, app_cap_module)

    return cap_module_path


def _ensure_tool_capability_package(
    capabilities_dir: Path,
    cloud_root: Path,
    capability_name: str,
) -> Optional[Path]:
    """Ensure `app.capabilities.<capability_name>` points to the tool capability."""
    possible_dir_names = [
        capability_name,
        capability_name.replace("_", "-"),
        capability_name.replace("-", "_"),
    ]
    tool_capability_dir = None
    for dir_name in possible_dir_names:
        candidate_dir = capabilities_dir / dir_name
        if candidate_dir.exists():
            tool_capability_dir = candidate_dir
            break

    if tool_capability_dir is None:
        return None

    app_cap_module_path = f"app.capabilities.{capability_name}"
    if app_cap_module_path not in sys.modules:
        if "app" not in sys.modules:
            try:
                importlib.import_module("app")
            except Exception:
                app_module = types.ModuleType("app")
                app_module.__path__ = [str(cloud_root)]
                init_file = cloud_root / "__init__.py"
                if init_file.exists():
                    spec = importlib.util.spec_from_file_location(
                        "app",
                        init_file,
                        submodule_search_locations=[str(cloud_root)],
                    )
                    if spec:
                        app_module.__spec__ = spec
                sys.modules["app"] = app_module

        app_capabilities_path = "app.capabilities"
        if app_capabilities_path not in sys.modules:
            app_capabilities_module = types.ModuleType(app_capabilities_path)
            app_capabilities_module.__path__ = [str(tool_capability_dir.parent)]
            capabilities_init = tool_capability_dir.parent / "__init__.py"
            if not capabilities_init.exists():
                capabilities_init.touch()
            if capabilities_init.exists():
                spec = importlib.util.spec_from_file_location(
                    app_capabilities_path,
                    capabilities_init,
                    submodule_search_locations=[str(tool_capability_dir.parent)],
                )
                if spec:
                    app_capabilities_module.__spec__ = spec
            sys.modules[app_capabilities_path] = app_capabilities_module
            if not hasattr(sys.modules["app"], "capabilities"):
                setattr(sys.modules["app"], "capabilities", app_capabilities_module)

        app_cap_module = types.ModuleType(app_cap_module_path)
        app_cap_module.__path__ = [str(tool_capability_dir)]
        init_file = tool_capability_dir / "__init__.py"
        if init_file.exists():
            spec = importlib.util.spec_from_file_location(
                app_cap_module_path,
                init_file,
                submodule_search_locations=[str(tool_capability_dir)],
            )
            if spec:
                app_cap_module.__spec__ = spec

        sys.modules[app_cap_module_path] = app_cap_module
        setattr(sys.modules["app.capabilities"], capability_name, app_cap_module)
        logger.debug(
            f"Created app.capabilities.{capability_name} module for tool validation, pointing to {tool_capability_dir}"
        )

    return tool_capability_dir


def _ensure_importable_tool_parent(
    module_path: str,
    capabilities_dir: Path,
) -> None:
    """Ensure app.capabilities parents have package metadata before import."""
    if not (
        module_path.startswith("capabilities.")
        or module_path.startswith("app.capabilities.")
    ):
        return

    if module_path.startswith("app.capabilities."):
        capability_parts = module_path.replace("app.capabilities.", "").split(".")
        capability_name = capability_parts[0] if capability_parts else None
    else:
        capability_parts = module_path.split(".")
        capability_name = capability_parts[1] if len(capability_parts) >= 2 else None

    if not capability_name:
        return

    app_capabilities_path = "app.capabilities"
    if app_capabilities_path not in sys.modules:
        if "app" not in sys.modules:
            app_module = types.ModuleType("app")
            sys.modules["app"] = app_module
        app_capabilities_module = types.ModuleType(app_capabilities_path)
        app_capabilities_module.__path__ = [str(capabilities_dir)]
        sys.modules[app_capabilities_path] = app_capabilities_module
        setattr(sys.modules["app"], "capabilities", app_capabilities_module)

    app_capabilities_module = sys.modules[app_capabilities_path]
    if (
        not hasattr(app_capabilities_module, "__spec__")
        or app_capabilities_module.__spec__ is None
    ):
        capabilities_init = capabilities_dir / "__init__.py"
        if not capabilities_init.exists():
            capabilities_init.touch()
        if capabilities_init.exists():
            spec = importlib.util.spec_from_file_location(
                app_capabilities_path,
                capabilities_init,
                submodule_search_locations=[str(capabilities_dir)],
            )
            if spec:
                app_capabilities_module.__spec__ = spec
                logger.debug(
                    f"Set __spec__ for {app_capabilities_path} before importing {module_path}"
                )

    app_cap_path = f"app.capabilities.{capability_name}"
    if app_cap_path not in sys.modules:
        cap_dir = capabilities_dir / capability_name
        if cap_dir.exists():
            app_cap_module = types.ModuleType(app_cap_path)
            app_cap_module.__path__ = [str(cap_dir)]
            sys.modules[app_cap_path] = app_cap_module
            setattr(sys.modules[app_capabilities_path], capability_name, app_cap_module)

    if app_cap_path not in sys.modules:
        return

    app_cap_module = sys.modules[app_cap_path]
    if hasattr(app_cap_module, "__spec__") and app_cap_module.__spec__ is not None:
        return

    cap_dir = capabilities_dir / capability_name
    init_file = cap_dir / "__init__.py"
    if not init_file.exists():
        return

    spec = importlib.util.spec_from_file_location(
        app_cap_path,
        init_file,
        submodule_search_locations=[str(cap_dir)],
    )
    if spec:
        app_cap_module.__spec__ = spec
        logger.debug(
            f"Set __spec__ for {app_cap_path} before importing {module_path}"
        )
