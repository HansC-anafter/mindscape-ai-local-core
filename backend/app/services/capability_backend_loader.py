"""Resolve capability backend callables from canonical or unpacked pack modules."""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.runtime_contract_paths import (
    prepend_import_paths,
    resolve_capability_runtime_import_roots,
)

logger = logging.getLogger(__name__)


def _normalize_module_path(module_path: str) -> str:
    if module_path.startswith("backend."):
        return module_path
    if module_path.startswith("app."):
        return f"backend.{module_path}"
    if module_path.startswith("capabilities."):
        return f"backend.app.{module_path}"
    return module_path


def _load_unpacked_pack_module(
    *,
    capability_dir: Path,
    raw_module_path: str,
    normalized_module_path: str,
) -> Optional[Any]:
    parts = raw_module_path.split(".")
    if len(parts) < 3 or parts[:2] != ["capabilities", capability_dir.name]:
        return None

    file_path = capability_dir.joinpath(*parts[2:]).with_suffix(".py")
    if not file_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(normalized_module_path, file_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    logger.debug("Loaded module %s from %s", normalized_module_path, file_path)
    return module


def resolve_capability_backend_callable(
    *,
    backend_path: str,
    capability_dir: Optional[Path],
) -> Callable[..., Any]:
    """Resolve one manifest backend target through the canonical import path."""

    if capability_dir is not None:
        prepend_import_paths(
            sys.path,
            resolve_capability_runtime_import_roots(capability_dir),
        )

    raw_module_path, target = backend_path.rsplit(":", 1)
    module_path = _normalize_module_path(raw_module_path)
    try:
        module = importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError) as import_error:
        module = (
            _load_unpacked_pack_module(
                capability_dir=capability_dir,
                raw_module_path=raw_module_path,
                normalized_module_path=module_path,
            )
            if capability_dir is not None
            else None
        )
        if module is None:
            raise import_error

    if "." not in target:
        return getattr(module, target)
    class_name, method_name = target.rsplit(".", 1)
    return getattr(getattr(module, class_name)(), method_name)
