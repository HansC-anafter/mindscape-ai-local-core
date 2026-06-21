"""Private helper checks for backend startup validation."""

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class CheckMessages:
    """Errors and warnings returned by a helper check."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


FORBIDDEN_MODULES = {"capabilities", "backend.app.capabilities"}
FORBIDDEN_PREFIXES = ("capabilities.", "backend.app.capabilities.")


def load_yaml_file(file_path: Path) -> tuple[Any, Optional[Exception]]:
    """Load a YAML file and return the parsed payload or the parse/read error."""

    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle), None
    except Exception as exc:
        return None, exc


def is_shim_file(file_path: Path) -> bool:
    """Return whether a Python file is an import compatibility shim."""

    file_name = file_path.name
    parent_dir = file_path.parent.name
    return (
        file_name.startswith("shim_")
        or file_name.endswith("_shim.py")
        or file_name.endswith("_compat.py")
        or parent_dir == "shims"
        or parent_dir == "_compat"
    )


def _parse_python_file(file_path: Path) -> tuple[Optional[ast.AST], Optional[SyntaxError]]:
    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    try:
        return ast.parse(content, filename=str(file_path)), None
    except SyntaxError as exc:
        return None, exc


def _is_forbidden_import(module_name: str) -> bool:
    if module_name in FORBIDDEN_MODULES:
        return True
    return any(module_name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


class _ForbiddenImportChecker(ast.NodeVisitor):
    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            module_name = alias.name
            if _is_forbidden_import(module_name):
                self.errors.append(f"Line {node.lineno}: import {module_name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and _is_forbidden_import(node.module):
            self.errors.append(f"Line {node.lineno}: from {node.module} import ...")
        self.generic_visit(node)


def check_file_imports_ast(
    file_path: Path,
    *,
    strict_syntax: bool,
    strict_validation: bool,
) -> CheckMessages:
    """Check one Python file for forbidden capability imports."""

    result = CheckMessages()
    if is_shim_file(file_path):
        return result

    try:
        tree, syntax_error = _parse_python_file(file_path)
    except Exception:
        return result

    if syntax_error:
        if strict_syntax or strict_validation:
            result.errors.append(
                f"File {file_path}: SyntaxError at line {syntax_error.lineno or 1}: {syntax_error.msg}"
            )
        return result

    checker = _ForbiddenImportChecker()
    checker.visit(tree)

    for error in checker.errors:
        message = f"File {file_path}: {error} - Use 'capabilities.*' instead (mindscape.capabilities.* is deprecated)"
        if strict_validation:
            result.errors.append(message)
        else:
            result.warnings.append(message)

    return result


class _RouterPrefixChecker(ast.NodeVisitor):
    def __init__(self):
        self.violations: list[int] = []

    def visit_Call(self, node: ast.Call):
        is_api_router = (
            isinstance(node.func, ast.Name) and node.func.id == "APIRouter"
        ) or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "APIRouter"
        )

        if is_api_router:
            for keyword in node.keywords:
                if keyword.arg == "prefix":
                    self.violations.append(node.lineno)
        self.generic_visit(node)


def check_router_prefix_ast(file_path: Path, *, strict_mode: bool) -> CheckMessages:
    """Check one capability API file for APIRouter prefix declarations."""

    result = CheckMessages()
    try:
        tree, syntax_error = _parse_python_file(file_path)
    except Exception:
        return result

    if syntax_error:
        return result

    checker = _RouterPrefixChecker()
    checker.visit(tree)

    for line_no in checker.violations:
        message = (
            f"File {file_path}: Line {line_no}: "
            "APIRouter must NOT have prefix parameter (Option A rule). "
            "Prefix should be defined in manifest.yaml only."
        )
        if strict_mode:
            result.errors.append(message)
        else:
            result.warnings.append(message)

    return result


def validate_manifest_schema(manifest: Any, schema: Any) -> Optional[str]:
    """Return the JSON schema validation error message, if validation fails."""

    if not schema:
        return None

    try:
        from jsonschema import ValidationError as JsonSchemaValidationError
        from jsonschema import validate

        manifest_json = json.loads(json.dumps(manifest))
        validate(instance=manifest_json, schema=schema)
    except ImportError:
        return None
    except JsonSchemaValidationError as exc:
        return exc.message
    except Exception:
        return None

    return None
