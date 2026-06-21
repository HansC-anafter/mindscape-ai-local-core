from pathlib import Path

from backend.app.mindscape.startup.validator_checks import (
    check_file_imports_ast,
    check_router_prefix_ast,
    validate_manifest_schema,
)
from backend.app.mindscape.startup.validators import StartupValidator


def test_check_file_imports_ast_reports_forbidden_imports_in_strict_mode(tmp_path: Path):
    source = tmp_path / "bad_imports.py"
    source.write_text(
        "import capabilities\nfrom backend.app.capabilities.demo import router\n",
        encoding="utf-8",
    )

    result = check_file_imports_ast(source, strict_syntax=False, strict_validation=True)

    assert len(result.errors) == 2
    assert "Line 1: import capabilities" in result.errors[0]
    assert "Line 2: from backend.app.capabilities.demo import ..." in result.errors[1]
    assert result.warnings == []


def test_check_file_imports_ast_downgrades_forbidden_imports_when_not_strict(tmp_path: Path):
    source = tmp_path / "bad_imports.py"
    source.write_text("import capabilities\n", encoding="utf-8")

    result = check_file_imports_ast(source, strict_syntax=False, strict_validation=False)

    assert result.errors == []
    assert len(result.warnings) == 1
    assert "Line 1: import capabilities" in result.warnings[0]


def test_check_file_imports_ast_respects_syntax_strictness(tmp_path: Path):
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n", encoding="utf-8")

    relaxed = check_file_imports_ast(source, strict_syntax=False, strict_validation=False)
    strict = check_file_imports_ast(source, strict_syntax=True, strict_validation=False)

    assert relaxed.errors == []
    assert relaxed.warnings == []
    assert len(strict.errors) == 1
    assert "SyntaxError" in strict.errors[0]


def test_check_router_prefix_ast_maps_violations_to_errors_or_warnings(tmp_path: Path):
    source = tmp_path / "api.py"
    source.write_text(
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/demo')\n",
        encoding="utf-8",
    )

    strict = check_router_prefix_ast(source, strict_mode=True)
    relaxed = check_router_prefix_ast(source, strict_mode=False)

    assert len(strict.errors) == 1
    assert "APIRouter must NOT have prefix parameter" in strict.errors[0]
    assert strict.warnings == []
    assert relaxed.errors == []
    assert len(relaxed.warnings) == 1


def test_validate_manifest_schema_returns_validation_error_message():
    schema = {
        "type": "object",
        "required": ["portability"],
        "properties": {
            "portability": {"type": "object"},
        },
    }

    assert validate_manifest_schema({"code": "demo"}, schema) == "'portability' is a required property"


def test_startup_validator_route_conflict_check_skips_head_and_records_duplicate_get():
    class Route:
        def __init__(self, path: str, methods: set[str]):
            self.path = path
            self.methods = methods

    class App:
        routes = [
            Route("/demo", {"GET", "HEAD"}),
            Route("/demo", {"GET"}),
            Route("/demo", {"POST"}),
        ]

    validator = StartupValidator(App())
    validator._validate_route_conflicts()

    assert validator.errors == ["Route conflict: GET /demo is registered multiple times"]
    assert validator.warnings == []
