"""
Startup validators.

Run lightweight startup checks that verify route, dependency, import, router, and
manifest contracts before the backend accepts traffic.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Tuple

from .validator_checks import (
    check_file_imports_ast,
    check_router_prefix_ast,
    load_yaml_file,
    validate_manifest_schema,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Collected startup validation result."""

    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StartupValidator:
    """
    Backend startup validator.

    The validator runs route conflict checks, dependency checks, capability
    degradation status checks, import path checks, router prefix checks, and
    manifest checks in a fixed order.
    """

    def __init__(self, app=None):
        self.app = app
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> bool:
        """Run every startup validation gate and return whether startup passed."""

        self._validate_route_conflicts()
        self._validate_required_dependencies()
        self._validate_capability_status()
        self._validate_import_paths()
        self._validate_router_prefix()
        self._validate_manifests()

        if self.errors:
            for error in self.errors:
                logger.error(f"STARTUP VALIDATION ERROR: {error}")
            logger.error(
                f"Startup validation failed with {len(self.errors)} error(s). "
                "Application may not function correctly."
            )
            return False

        if self.warnings:
            for warning in self.warnings:
                logger.warning(f"STARTUP VALIDATION WARNING: {warning}")

        logger.info("All startup validations passed")
        return True

    def _validate_route_conflicts(self):
        """Check for duplicate method/path route registrations."""

        if self.app is None:
            logger.debug("No app provided, skipping route conflict validation")
            return

        registered_routes: Set[Tuple[str, str]] = set()

        for route in self.app.routes:
            methods = getattr(route, "methods", set())
            path = getattr(route, "path", "")

            if not path:
                continue

            for method in methods:
                if method == "HEAD":
                    continue

                key = (method, path)
                if key in registered_routes:
                    self.errors.append(
                        f"Route conflict: {method} {path} is registered multiple times"
                    )
                registered_routes.add(key)

        logger.debug(f"Validated {len(registered_routes)} routes for conflicts")

    def _validate_required_dependencies(self):
        """Check capability required dependencies declared in manifests."""

        try:
            from mindscape import get_capabilities_base_path
            from mindscape.runtime.degradation import DegradationRegistry

            _ = DegradationRegistry
            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith("_"):
                    continue

                manifest_path = cap_dir / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                manifest, error = load_yaml_file(manifest_path)
                if error:
                    continue

                dependencies = manifest.get("dependencies", {})
                required_deps = dependencies.get("required", [])

                for dep in required_deps:
                    if not self._is_dependency_available(dep):
                        self.errors.append(
                            f"Capability '{cap_dir.name}' missing required dependency: {dep}"
                        )
        except ImportError as exc:
            logger.debug(f"Could not validate dependencies: {exc}")

    def _validate_capability_status(self):
        """Add warnings for unavailable or degraded capabilities."""

        try:
            from mindscape.runtime.degradation import DegradationRegistry

            registry = DegradationRegistry()
            statuses = registry.get_all_statuses()

            for code, status in statuses.items():
                if status.status == "unavailable":
                    self.warnings.append(
                        f"Capability '{code}' is unavailable due to missing dependencies: "
                        f"{status.missing_dependencies}"
                    )
                elif status.status == "degraded":
                    self.warnings.append(
                        f"Capability '{code}' running in degraded mode. "
                        f"Degraded features: {status.degraded_features}"
                    )
        except ImportError:
            pass

    def _validate_import_paths(self):
        """Check capability Python imports with the same AST rules used by CI."""

        try:
            from mindscape import get_capabilities_base_path

            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith("_"):
                    continue

                for py_file in cap_dir.rglob("*.py"):
                    result = check_file_imports_ast(
                        py_file,
                        strict_syntax=os.getenv("STRICT_SYNTAX", "0") == "1",
                        strict_validation=os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1",
                    )
                    self.errors.extend(result.errors)
                    self.warnings.extend(result.warnings)
        except Exception as exc:
            logger.debug(f"Could not validate import paths: {exc}")

    def _validate_router_prefix(self):
        """Check that capability API routers do not set their own prefix."""

        try:
            from mindscape import get_capabilities_base_path

            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith("_"):
                    continue

                manifest_path = cap_dir / "manifest.yaml"
                if manifest_path.exists():
                    _manifest, _error = load_yaml_file(manifest_path)

                api_dir = cap_dir / "api"
                if api_dir.exists() and api_dir.is_dir():
                    for py_file in api_dir.rglob("*.py"):
                        result = check_router_prefix_ast(
                            py_file,
                            strict_mode=os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1",
                        )
                        self.errors.extend(result.errors)
                        self.warnings.extend(result.warnings)
        except Exception as exc:
            logger.debug(f"Could not validate router prefix: {exc}")

    def _validate_manifests(self):
        """Check capability manifest files against required fields and schema."""

        try:
            from mindscape import get_capabilities_base_path

            capabilities_dir = get_capabilities_base_path()
            schema_path = Path(__file__).parent.parent.parent.parent.parent / "schemas" / "manifest.schema.yaml"
            schema = None
            if schema_path.exists():
                schema, _schema_error = load_yaml_file(schema_path)

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith("_"):
                    continue

                manifest_path = cap_dir / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                manifest, error = load_yaml_file(manifest_path)
                if error:
                    strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                    message = f"Capability '{cap_dir.name}': Failed to parse manifest.yaml: {error}"
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)
                    continue

                if not manifest:
                    continue

                strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                if "portability" not in manifest:
                    message = (
                        f"Capability '{cap_dir.name}': Missing required field 'portability'. "
                        "Add portability declaration to support cross-environment deployment."
                    )
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)

                schema_error = validate_manifest_schema(manifest, schema)
                if schema_error:
                    message = f"Capability '{cap_dir.name}': Manifest schema validation failed: {schema_error}"
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)
        except Exception as exc:
            logger.debug(f"Could not validate manifests: {exc}")

    def _is_dependency_available(self, dep_name: str) -> bool:
        """Return whether a required dependency can be imported."""

        special_deps = {
            "core_llm": "capabilities.core_llm",
            "database": "backend.app.database",
        }
        module_name = special_deps.get(dep_name, dep_name)

        try:
            __import__(module_name.replace(".", "_"))
            return True
        except ImportError:
            try:
                import importlib

                importlib.import_module(module_name)
                return True
            except ImportError:
                return False

    def get_result(self) -> ValidationResult:
        """Return a copy of the collected validation result."""

        return ValidationResult(
            passed=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
        )


def run_startup_validation(app=None) -> bool:
    """
    Run startup validation and return whether startup passed.

    Strict mode logs a critical message on failure. The caller decides whether to
    abort application startup.
    """

    strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "0") == "1"

    validator = StartupValidator(app)
    passed = validator.validate_all()

    if not passed and strict_mode:
        logger.critical(
            "Startup validation failed in strict mode. "
            "Set MINDSCAPE_STRICT_VALIDATION=0 to continue anyway (not recommended)."
        )

    return passed
