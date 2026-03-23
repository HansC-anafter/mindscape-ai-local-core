"""
Tool validation helpers for installed playbooks.
"""

import importlib
import importlib.util
import inspect
import json
import logging
import sys
import types
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


def _load_optional_python_packages(
    capabilities_dir: Path,
    capability_code: str,
) -> List[str]:
    """Read optional Python packages declared in the capability manifest."""
    possible_dir_names = [
        capability_code,
        capability_code.replace("_", "-"),
        capability_code.replace("-", "_"),
    ]
    for dir_name in possible_dir_names:
        manifest_path = capabilities_dir / dir_name / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = yaml.safe_load(file) or {}
            deps = manifest.get("dependencies", {})
            python_packages = deps.get("python_packages", {})
            optional_packages = python_packages.get("optional", [])
            if optional_packages:
                logger.debug(
                    f"Found optional Python packages in manifest: {optional_packages}"
                )
            return optional_packages
        except Exception as exc:
            logger.debug(
                f"Failed to read manifest for optional Python packages: {exc}"
            )
            return []
    return []


def _load_required_capabilities(specs_dir: Path, playbook_code: str) -> List[str]:
    """Read required capabilities from the installed playbook spec."""
    spec_path = specs_dir / f"{playbook_code}.json"
    if not spec_path.exists():
        return []
    try:
        with open(spec_path, "r", encoding="utf-8") as file:
            spec = json.load(file)
        return spec.get("required_capabilities", [])
    except Exception as exc:
        logger.warning(
            f"Failed to read playbook spec for required_capabilities: {exc}"
        )
        return []


def _get_backend_from_manifest(
    capabilities_dir: Path,
    manifest_tool_backends: Dict[str, Dict[str, str]],
    capability_name: str,
    tool_name: str,
) -> Optional[str]:
    """Resolve a tool backend from the capability manifest."""
    if capability_name in manifest_tool_backends:
        return manifest_tool_backends[capability_name].get(tool_name)

    manifest_tool_backends[capability_name] = {}
    possible_dirs = [
        capability_name,
        capability_name.replace("_", "-"),
        capability_name.replace("-", "_"),
    ]

    manifest_path = None
    for dir_name in possible_dirs:
        candidate_path = capabilities_dir / dir_name / "manifest.yaml"
        if candidate_path.exists():
            manifest_path = candidate_path
            break

    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = yaml.safe_load(file) or {}
            for tool_config in manifest.get("tools", []):
                if not isinstance(tool_config, dict):
                    continue
                code = tool_config.get("code") or tool_config.get("name")
                backend_path = tool_config.get("backend")
                if code and backend_path:
                    manifest_tool_backends[capability_name][code] = backend_path
                    logger.debug(
                        f"Found tool backend from manifest: {capability_name}.{code} -> {backend_path}"
                    )
        except Exception as exc:
            logger.warning(
                f"Failed to read manifest for capability {capability_name} from {manifest_path}: {exc}"
            )
    else:
        logger.debug(
            "Manifest not found for capability %s, tried paths: %s",
            capability_name,
            [str(capabilities_dir / dirname / "manifest.yaml") for dirname in possible_dirs],
        )

    return manifest_tool_backends[capability_name].get(tool_name)


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


def _preload_models(
    capability_dir: Path, cap_module_path: str, capability_code: str
) -> None:
    """Preload capability models and database dependency modules."""
    models_module_path = f"capabilities.{capability_code}.models"
    models_dir = capability_dir / "models"
    models_file = capability_dir / "models.py"

    if models_module_path not in sys.modules:
        try:
            if models_dir.exists() and models_dir.is_dir():
                models_init = models_dir / "__init__.py"
                if models_init.exists():
                    models_pkg = types.ModuleType(models_module_path)
                    models_pkg.__path__ = [str(models_dir)]
                    models_pkg.__file__ = str(models_init)
                    sys.modules[models_module_path] = models_pkg
                    setattr(sys.modules[cap_module_path], "models", models_pkg)
                    models_spec = importlib.util.spec_from_file_location(
                        models_module_path,
                        models_init,
                        submodule_search_locations=[str(models_dir)],
                    )
                    if models_spec and models_spec.loader:
                        models_spec.loader.exec_module(models_pkg)
                        logger.info(f"Pre-loaded models package from {models_init}")
                else:
                    logger.warning(
                        f"models/ directory exists but no __init__.py found: {models_dir}"
                    )
            elif models_file.exists():
                models_spec = importlib.util.spec_from_file_location(
                    models_module_path,
                    models_file,
                )
                if models_spec and models_spec.loader:
                    models_module = importlib.util.module_from_spec(models_spec)
                    models_spec.loader.exec_module(models_module)
                    sys.modules[models_module_path] = models_module
                    setattr(sys.modules[cap_module_path], "models", models_module)
                    logger.info(f"Pre-loaded models.py from {models_file}")
            else:
                logger.debug(
                    f"No models.py or models/ directory found in {capability_dir}"
                )
        except Exception as exc:
            logger.warning(f"Failed to pre-load models: {exc}")
            logger.debug("Model preload traceback", exc_info=True)

    db_dep_path = capability_dir / "database_dependency.py"
    db_dep_module_path = f"capabilities.{capability_code}.database_dependency"
    if db_dep_path.exists() and db_dep_module_path not in sys.modules:
        try:
            db_dep_spec = importlib.util.spec_from_file_location(
                db_dep_module_path,
                db_dep_path,
            )
            if db_dep_spec and db_dep_spec.loader:
                db_dep_module = importlib.util.module_from_spec(db_dep_spec)
                db_dep_spec.loader.exec_module(db_dep_module)
                sys.modules[db_dep_module_path] = db_dep_module
                setattr(
                    sys.modules[cap_module_path],
                    "database_dependency",
                    db_dep_module,
                )
        except Exception as exc:
            logger.debug(f"Failed to pre-load database_dependency.py: {exc}")


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


def _preload_tool_models(capability_name: str) -> None:
    """Preload tool capability models and normalize `Plan` exposure when available."""
    models_module_path = f"capabilities.{capability_name}.models"
    logger.info(
        f"Pre-loading {models_module_path} for tool validation"
    )
    logger.debug(f"sys.path before model pre-load: {sys.path[:5]}... (showing first 5)")

    try:
        models_module = importlib.import_module(models_module_path)
        logger.info(
            f"Module '{models_module_path}' loaded, checking Plan availability..."
        )
        logger.debug(f"Module in sys.modules: {models_module_path in sys.modules}")
        logger.debug(f"Module object: {models_module}")
        logger.debug(
            f"Module __file__: {getattr(models_module, '__file__', 'N/A')}"
        )

        if hasattr(models_module, "Plan") and models_module.Plan is not None:
            logger.info(
                "Pre-loaded %s with Plan=%s, source=%s",
                models_module_path,
                models_module.Plan,
                getattr(models_module, "get_model_source", lambda: "unknown")(),
            )
            if models_module_path in sys.modules:
                sys.modules[models_module_path].Plan = models_module.Plan
            if "Plan" not in models_module.__dict__:
                models_module.Plan = models_module.Plan
        else:
            logger.warning(f"Pre-loaded {models_module_path} but Plan is None")
            logger.debug(
                "Module attributes: %s",
                [
                    attr
                    for attr in dir(models_module)
                    if not attr.startswith("_")
                ][:10],
            )
    except Exception as exc:
        logger.warning(
            f"Preload capability models failed for {capability_name}: {exc}"
        )
        logger.debug("Capability model preload traceback", exc_info=True)

    cached_module = sys.modules.get(models_module_path)
    if cached_module is None:
        return

    logger.debug(
        "Checking cached module state: Plan=%s",
        "available"
        if hasattr(cached_module, "Plan") and cached_module.Plan is not None
        else "NOT available",
    )
    if hasattr(cached_module, "Plan") and cached_module.Plan is not None:
        logger.info(f"Verified Plan is available in sys.modules['{models_module_path}']")
        return

    logger.warning("Plan not available in cached module, attempting to refresh it...")
    try:
        fresh_module = importlib.import_module(models_module_path)
        if hasattr(fresh_module, "Plan") and fresh_module.Plan is not None:
            sys.modules[models_module_path].Plan = fresh_module.Plan
            logger.info("Set Plan from fresh import")
    except Exception as exc:
        logger.warning(f"Failed to set Plan from fresh import: {exc}")


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


def _is_optional_import_error(
    error_message: str, optional_python_packages: List[str]
) -> bool:
    """Determine whether an import failure should be downgraded to a warning."""
    if optional_python_packages:
        for package in optional_python_packages:
            if str(package).lower() in error_message.lower():
                return True

    fallback_markers = [
        "langchain",
        "asyncpg",
        "services.divi",
        "capabilities.wordpress",
        "database.models.divi",
    ]
    return any(marker in error_message.lower() for marker in fallback_markers)


def validate_tools_direct_call(
    playbook_code: str,
    capability_code: str,
    capabilities_dir: Path,
    specs_dir: Path,
) -> Tuple[List[str], List[str]]:
    """Validate tool backends referenced by a playbook without executing them."""
    errors: List[str] = []
    warnings: List[str] = []
    optional_python_packages = _load_optional_python_packages(
        capabilities_dir, capability_code
    )
    required_capabilities = _load_required_capabilities(specs_dir, playbook_code)
    manifest_tool_backends: Dict[str, Dict[str, str]] = {}

    try:
        capability_dir, cloud_root, _backend_root = _discover_capability_dir(
            capabilities_dir, capability_code
        )
        if capability_dir and cloud_root:
            cap_module_path = _ensure_capabilities_package(
                capabilities_dir,
                capability_dir,
                capability_code,
            )
            _preload_models(capability_dir, cap_module_path, capability_code)

        spec_path = (
            capabilities_dir
            / capability_code
            / "playbooks"
            / "specs"
            / f"{playbook_code}.json"
        )
        if not spec_path.exists():
            spec_path = specs_dir / f"{playbook_code}.json"
            if not spec_path.exists():
                errors.append(f"Playbook spec not found: {playbook_code}.json")
                return errors, warnings

        with open(spec_path, "r", encoding="utf-8") as file:
            spec = json.load(file)

        steps = spec.get("steps", [])
        if not isinstance(steps, list):
            return errors, warnings

        try:
            from backend.app.shared.tool_executor import ToolExecutor

            _tool_executor = ToolExecutor()
        except ImportError as exc:
            errors.append(f"Failed to import ToolExecutor: {exc}")
            return errors, warnings

        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            step_id = step.get("id", f"step_{step_index}")
            tool_slot = step.get("tool_slot")
            step_condition = step.get("condition")

            if not tool_slot or tool_slot.startswith("core."):
                continue

            tool_capability = tool_slot.split(".", 1)[0] if "." in tool_slot else None
            is_required = (
                tool_capability in required_capabilities if tool_capability else False
            )

            if not is_required and step_condition:
                logger.debug(
                    f"Step '{step_id}': Tool '{tool_slot}' is optional (has condition and not in required_capabilities), skipping validation"
                )
                continue

            try:
                if "." not in tool_slot:
                    logger.debug(
                        f"Step '{step_id}': Non-capability tool '{tool_slot}' skipped (requires runtime)"
                    )
                    continue

                capability_name, tool_name = tool_slot.split(".", 1)
                backend_path = _get_backend_from_manifest(
                    capabilities_dir,
                    manifest_tool_backends,
                    capability_name,
                    tool_name,
                )
                if backend_path:
                    logger.debug(
                        f"Step '{step_id}': Found backend from manifest: {capability_name}.{tool_name} -> {backend_path}"
                    )
                else:
                    logger.debug(
                        f"Step '{step_id}': Backend not found in manifest for {capability_name}.{tool_name}, trying registry..."
                    )
                    from backend.app.services.capability_registry import get_tool_backend

                    backend_path = get_tool_backend(capability_name, tool_name)
                    if backend_path:
                        logger.debug(
                            f"Step '{step_id}': Found backend from registry: {capability_name}.{tool_name} -> {backend_path}"
                        )

                tool_capability_dir = None
                if cloud_root:
                    tool_capability_dir = _ensure_tool_capability_package(
                        capabilities_dir,
                        cloud_root,
                        capability_name,
                    )

                if backend_path is None:
                    if not is_required:
                        logger.warning(
                            f"Step '{step_id}': Tool '{tool_slot}' from optional capability '{capability_name}' not found, skipping validation"
                        )
                        continue
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' backend not found (required capability)"
                    )
                    continue

                if ":" not in backend_path:
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' invalid backend format: '{backend_path}'"
                    )
                    continue

                module_path, target = backend_path.rsplit(":", 1)
                if module_path.startswith("app.capabilities."):
                    pass
                elif module_path.startswith("app."):
                    module_path = "backend." + module_path

                _preload_tool_models(capability_name)
                logger.info(f"Importing tool file: {module_path}")
                logger.debug(
                    f"sys.path before tool import: {sys.path[:5]}... (showing first 5)"
                )
                _ensure_importable_tool_parent(module_path, capabilities_dir)

                try:
                    module = importlib.import_module(module_path)
                except (ImportError, ModuleNotFoundError, ValueError) as import_error:
                    error_message = str(import_error)
                    if _is_optional_import_error(
                        error_message, optional_python_packages
                    ):
                        warnings.append(
                            f"Step '{step_id}': Tool '{tool_slot}' has optional dependency issue: {import_error}. "
                            "Tool will be available once dependencies are installed."
                        )
                        logger.warning(
                            f"Step '{step_id}': Tool '{tool_slot}' import failed due to optional dependency: {import_error}"
                        )
                        continue
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' validation error: {import_error}"
                    )
                    continue

                try:
                    if "." in target:
                        class_name, method_name = target.rsplit(".", 1)
                        cls = getattr(module, class_name, None)
                        if cls is None:
                            errors.append(
                                f"Step '{step_id}': Tool '{tool_slot}' class '{class_name}' not found in module"
                            )
                            continue
                        func = getattr(cls, method_name, None)
                    else:
                        func = getattr(module, target, None)

                    if func is None:
                        warnings.append(
                            f"Step '{step_id}': Tool '{tool_slot}' function '{target}' not found in module (may not be implemented yet). "
                            "Tool will be available once implementation is complete."
                        )
                        logger.warning(
                            f"Step '{step_id}': Tool '{tool_slot}' function '{target}' not found in module (may not be implemented yet)"
                        )
                        continue

                    if not callable(func):
                        errors.append(
                            f"Step '{step_id}': Tool '{tool_slot}' '{backend_path}' is not a callable object"
                        )
                        continue

                    signature = inspect.signature(func)
                    logger.debug(
                        f"Step '{step_id}': Tool '{tool_slot}' signature validated: {signature}"
                    )
                except Exception as exc:
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' validation error: {exc}"
                    )
            except Exception as exc:
                errors.append(
                    f"Step '{step_id}': Tool '{tool_slot}' call test failed: {exc}"
                )

        if errors:
            logger.error(
                f"Playbook {playbook_code} tool call test failed: {len(errors)} error(s)"
            )

    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in playbook spec: {exc}")
    except Exception as exc:
        errors.append(f"Error validating tool calls: {exc}")

    return errors, warnings
