"""
Startup Validators

在應用啟動時執行驗證，確保系統配置正確。
"""

import sys
import os
import logging
import ast
import yaml
from typing import List, Set, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """驗證結果"""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StartupValidator:
    """
    啟動時驗證器

    在 FastAPI 應用啟動時執行以下驗證：
    1. 路由衝突檢查
    2. 必要依賴檢查
    3. Import 路徑檢查（可選）
    """

    def __init__(self, app=None):
        """
        初始化驗證器

        Args:
            app: FastAPI 應用實例（可選）
        """
        self.app = app
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> bool:
        """
        執行所有驗證

        Returns:
            True 如果所有驗證通過，否則 False
        """
        self._validate_route_conflicts()
        self._validate_required_dependencies()
        self._validate_capability_status()
        self._validate_import_paths()
        self._validate_router_prefix()
        self._validate_manifests()

        # Record results
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

        logger.info("✅ All startup validations passed")
        return True

    def _validate_route_conflicts(self):
        """檢查路由衝突"""
        if self.app is None:
            logger.debug("No app provided, skipping route conflict validation")
            return

        registered_routes: Set[Tuple[str, str]] = set()

        for route in self.app.routes:
            methods = getattr(route, 'methods', set())
            path = getattr(route, 'path', '')

            if not path:
                continue

            for method in methods:
                if method == 'HEAD':
                    continue

                key = (method, path)
                if key in registered_routes:
                    self.errors.append(
                        f"Route conflict: {method} {path} is registered multiple times"
                    )
                registered_routes.add(key)

        logger.debug(f"Validated {len(registered_routes)} routes for conflicts")

    def _validate_required_dependencies(self):
        """檢查必要依賴"""
        try:
            from mindscape import get_capabilities_base_path
            from mindscape.runtime.degradation import DegradationRegistry
            import yaml

            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith('_'):
                    continue

                manifest_path = cap_dir / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = yaml.safe_load(f)
                except Exception:
                    continue

                # Check required dependencies
                dependencies = manifest.get('dependencies', {})
                required_deps = dependencies.get('required', [])

                for dep in required_deps:
                    if not self._is_dependency_available(dep):
                        self.errors.append(
                            f"Capability '{cap_dir.name}' missing required dependency: {dep}"
                        )
        except ImportError as e:
            logger.debug(f"Could not validate dependencies: {e}")

    def _validate_capability_status(self):
        """驗證 capability 狀態"""
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
            # DegradationRegistry unavailable, skip
            pass

    def _validate_import_paths(self):
        """檢查 import 路徑（使用 AST 解析，與 CI 驗證保持一致）"""
        try:
            from mindscape import get_capabilities_base_path
            import ast

            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith('_'):
                    continue

                for py_file in cap_dir.rglob("*.py"):
                    self._check_file_imports_ast(py_file)
        except Exception as e:
            logger.debug(f"Could not validate import paths: {e}")

    def _check_file_imports_ast(self, file_path: Path):
        """
        檢查單個文件的 import（使用 AST 解析）

        重用 CI 驗證的 AST 邏輯，避免兩套規則漂移。
        """
        # Skip shim files (strict check: filename or directory name match)
        file_name = file_path.name
        parent_dir = file_path.parent.name
        is_shim_file = (
            file_name.startswith("shim_") or
            file_name.endswith("_shim.py") or
            file_name.endswith("_compat.py") or
            parent_dir == "shims" or
            parent_dir == "_compat"
        )
        if is_shim_file:
            return

        # Use same rules as CI validation
        forbidden_modules = {"capabilities", "backend.app.capabilities"}
        forbidden_prefixes = [
            "capabilities.",
            "backend.app.capabilities.",
        ]

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Use AST parsing (consistent with CI validation)
            try:
                import ast
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                # Syntax error handling: determine if treated as error based on environment variable
                strict_syntax = os.getenv("STRICT_SYNTAX", "0") == "1"
                strict_validation = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"

                # If strict mode enabled, treat syntax error as validation failure
                if strict_syntax or strict_validation:
                    message = f"File {file_path}: SyntaxError at line {e.lineno or 1}: {e.msg}"
                    self.errors.append(message)
                # Otherwise skip (may be dynamically generated files, etc.)
                return

            # Use AST visitor to check
            class ImportChecker(ast.NodeVisitor):
                def __init__(self, file_path: Path):
                    self.file_path = file_path
                    self.errors = []

                def _is_forbidden(self, module_name: str) -> bool:
                    """Check if module name uses forbidden module name or prefix"""
                    # Check exact match (bare module)
                    if module_name in forbidden_modules:
                        return True
                    # Check prefix match
                    return any(module_name.startswith(prefix) for prefix in forbidden_prefixes)

                def visit_Import(self, node):
                    for alias in node.names:
                        module_name = alias.name
                        if self._is_forbidden(module_name):
                            self.errors.append(
                                f"Line {node.lineno}: import {module_name}"
                            )
                    self.generic_visit(node)

                def visit_ImportFrom(self, node):
                    if node.module and self._is_forbidden(node.module):
                        self.errors.append(
                            f"Line {node.lineno}: from {node.module} import ..."
                        )
                    self.generic_visit(node)

            checker = ImportChecker(file_path)
            checker.visit(tree)

            if checker.errors:
                strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"

                for error in checker.errors:
                    message = f"File {file_path}: {error} - Use 'capabilities.*' instead (mindscape.capabilities.* is deprecated)"

                    if strict_mode:
                        # Production strict mode: violations treated as errors, will block startup
                        self.errors.append(message)
                    else:
                        # Non-strict mode: only log warnings
                        self.warnings.append(message)
        except Exception:
            # Skip on read failure
            pass

    def _validate_router_prefix(self):
        """檢查 router prefix 規則（Option A：Router 不得設置 prefix）"""
        try:
            from mindscape import get_capabilities_base_path
            import ast
            import yaml

            capabilities_dir = get_capabilities_base_path()

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith('_'):
                    continue

                # Check if manifest has API definition
                manifest_path = cap_dir / "manifest.yaml"
                has_api = False
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = yaml.safe_load(f)
                        has_api = bool(manifest.get('apis') or manifest.get('capabilities'))
                    except Exception:
                        pass

                # Scan api/ directory
                api_dir = cap_dir / "api"
                if api_dir.exists() and api_dir.is_dir():
                    for py_file in api_dir.rglob("*.py"):
                        self._check_router_prefix_ast(py_file, cap_dir.name)
        except Exception as e:
            logger.debug(f"Could not validate router prefix: {e}")

    def _check_router_prefix_ast(self, file_path: Path, capability_name: str):
        """檢查 router 文件是否違反 prefix 規則"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            try:
                import ast
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError:
                return

            class RouterPrefixChecker(ast.NodeVisitor):
                def __init__(self, file_path: Path):
                    self.file_path = file_path
                    self.violations = []

                def visit_Call(self, node: ast.Call):
                    is_api_router = (
                        isinstance(node.func, ast.Name) and node.func.id == "APIRouter"
                    ) or (
                        isinstance(node.func, ast.Attribute) and node.func.attr == "APIRouter"
                    )

                    if is_api_router:
                        for kw in node.keywords:
                            if kw.arg == "prefix":
                                self.violations.append(node.lineno)
                    self.generic_visit(node)

            checker = RouterPrefixChecker(file_path)
            checker.visit(tree)

            if checker.violations:
                strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                for line_no in checker.violations:
                    message = (
                        f"File {file_path}: Line {line_no}: "
                        f"APIRouter must NOT have prefix parameter (Option A rule). "
                        f"Prefix should be defined in manifest.yaml only."
                    )
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)
        except Exception:
            pass

    def _validate_manifests(self):
        """檢查 manifest.yaml 是否符合 schema 要求"""
        try:
            from mindscape import get_capabilities_base_path
            import yaml
            import json

            capabilities_dir = get_capabilities_base_path()

            # Try to load JSON Schema
            schema_path = Path(__file__).parent.parent.parent.parent.parent / "schemas" / "manifest.schema.yaml"
            schema = None
            if schema_path.exists():
                try:
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        schema = yaml.safe_load(f)
                except Exception:
                    pass

            for cap_dir in capabilities_dir.iterdir():
                if not cap_dir.is_dir() or cap_dir.name.startswith('_'):
                    continue

                manifest_path = cap_dir / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = yaml.safe_load(f)
                except Exception as e:
                    strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                    message = f"Capability '{cap_dir.name}': Failed to parse manifest.yaml: {e}"
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)
                    continue

                if not manifest:
                    continue

                # Basic check: required fields
                if 'portability' not in manifest:
                    strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                    message = (
                        f"Capability '{cap_dir.name}': Missing required field 'portability'. "
                        "Add portability declaration to support cross-environment deployment."
                    )
                    if strict_mode:
                        self.errors.append(message)
                    else:
                        self.warnings.append(message)

                # JSON Schema validation (if available)
                if schema:
                    try:
                        from jsonschema import validate, ValidationError as JsonSchemaValidationError
                        manifest_json = json.loads(json.dumps(manifest))
                        validate(instance=manifest_json, schema=schema)
                    except ImportError:
                        # jsonschema unavailable, skip
                        pass
                    except JsonSchemaValidationError as e:
                        strict_mode = os.getenv("MINDSCAPE_STRICT_VALIDATION", "1") == "1"
                        message = (
                            f"Capability '{cap_dir.name}': Manifest schema validation failed: {e.message}"
                        )
                        if strict_mode:
                            self.errors.append(message)
                        else:
                            self.warnings.append(message)
                    except Exception:
                        # Skip on schema validation failure (does not block startup)
                        pass
        except Exception as e:
            logger.debug(f"Could not validate manifests: {e}")

    def _is_dependency_available(self, dep_name: str) -> bool:
        """
        Check if dependency is available

        Args:
            dep_name: Dependency name

        Returns:
            True if available
        """
        # Handle special dependency names
        special_deps = {
            'core_llm': 'capabilities.core_llm',
            'database': 'backend.app.database',
        }

        module_name = special_deps.get(dep_name, dep_name)

        try:
            __import__(module_name.replace('.', '_'))
            return True
        except ImportError:
            try:
                import importlib
                importlib.import_module(module_name)
                return True
            except ImportError:
                return False

    def get_result(self) -> ValidationResult:
        """獲取驗證結果"""
        return ValidationResult(
            passed=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy()
        )


def run_startup_validation(app=None) -> bool:
    """
    執行啟動驗證

    如果驗證失敗，應用應該考慮拒絕啟動（取決於配置）。

    Args:
        app: FastAPI 應用實例（可選）

    Returns:
        True 如果驗證通過

    用法：
        app = FastAPI()

        @app.on_event("startup")
        async def startup():
            if not run_startup_validation(app):
                if os.getenv("MINDSCAPE_STRICT_VALIDATION") == "1":
                    raise RuntimeError("Startup validation failed")
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


