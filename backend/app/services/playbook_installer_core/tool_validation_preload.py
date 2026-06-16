"""Model preload helpers for playbook tool validation."""

import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(f"{__package__}.tool_validation")


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


def _preload_tool_models(
    capability_name: str,
    preload_cache: Optional[Dict[str, str]] = None,
) -> None:
    """Preload tool capability models and normalize `Plan` exposure when available."""
    if preload_cache is not None and capability_name in preload_cache:
        logger.debug(
            "Skipping repeated preload for capabilities.%s.models (cached=%s)",
            capability_name,
            preload_cache[capability_name],
        )
        return

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
            if preload_cache is not None:
                preload_cache[capability_name] = "plan_available"
        else:
            logger.debug(
                "Pre-loaded %s without Plan export; continuing tool validation",
                models_module_path,
            )
            if preload_cache is not None:
                preload_cache[capability_name] = "no_plan"
    except Exception as exc:
        logger.warning(
            f"Preload capability models failed for {capability_name}: {exc}"
        )
        logger.debug("Capability model preload traceback", exc_info=True)
        if preload_cache is not None:
            preload_cache[capability_name] = f"error:{type(exc).__name__}"
