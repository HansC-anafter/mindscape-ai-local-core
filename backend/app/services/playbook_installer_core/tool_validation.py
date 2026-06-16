"""Tool validation facade for installed playbooks."""

import importlib
import inspect
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .tool_validation_manifest import (
    _get_backend_from_manifest,
    _is_optional_import_error,
    _load_optional_python_packages,
    _load_required_capabilities,
)
from .tool_validation_packages import (
    _discover_capability_dir,
    _ensure_capabilities_package,
    _ensure_importable_tool_parent,
    _ensure_tool_capability_package,
)
from .tool_validation_preload import _preload_models, _preload_tool_models

logger = logging.getLogger(__name__)


def validate_tools_direct_call(
    playbook_code: str,
    capability_code: str,
    capabilities_dir: Path,
    specs_dir: Path,
    tool_model_preload_cache: Optional[Dict[str, str]] = None,
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
                _ = tool_capability_dir

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

                _preload_tool_models(
                    capability_name,
                    preload_cache=tool_model_preload_cache,
                )
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
