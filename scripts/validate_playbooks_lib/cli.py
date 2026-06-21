import argparse
import json
from typing import List, Optional

from . import settings
from .models import PlaybookValidation, ValidationResult
from .validator import PlaybookValidator

_json_mode = False


def log(msg: str, level: str = "INFO") -> None:
    """Log with level prefix."""
    if _json_mode:
        return
    colors = {
        "INFO": "\033[0m",
        "PASS": "\033[92m",
        "FAIL": "\033[91m",
        "WARN": "\033[93m",
        "SKIP": "\033[94m",
    }
    reset = "\033[0m"
    color = colors.get(level, colors["INFO"])
    print(f"{color}[{level}]{reset} {msg}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate playbooks before deployment")
    parser.add_argument("--playbook", "-p", help="Specific playbook code to validate")
    parser.add_argument(
        "--capability", "-c", help="Specific capability pack to validate"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="Skip execution test, only validate structure",
    )
    args = parser.parse_args(argv)

    global _json_mode
    _json_mode = args.json

    if not args.json:
        log("=" * 70)
        log("PLAYBOOK VALIDATION")
        log(f"LLM_MOCK: {settings.LLM_MOCK}")
        log(f"BASE_URL: {settings.BASE_URL}")
        log("=" * 70)

    validator = PlaybookValidator()

    if args.skip_execution:
        validator._skip_execution = True

    playbooks = validator.discover_playbooks(capability=args.capability)

    if args.playbook:
        playbooks = [(c, p, s) for c, p, s in playbooks if p == args.playbook]

    if not playbooks:
        if not args.json:
            log("No playbooks found to validate", "WARN")
        return 1

    if not args.json:
        log(f"Found {len(playbooks)} playbooks to validate")
        log("")

    all_validations = []
    all_passed = True

    for capability, playbook_code, spec_path in playbooks:
        if not args.json:
            log("-" * 50)
            log(f"Validating: {capability}/{playbook_code}")
            log("-" * 50)

        try:
            validation = validator.validate_playbook(
                capability, playbook_code, spec_path
            )
            all_validations.append(validation)
        except Exception as e:
            validation = PlaybookValidation(
                playbook_code=playbook_code, capability=capability
            )
            validation.results.append(
                ValidationResult(
                    check_name="validation_error",
                    passed=False,
                    message=f"Validation error: {str(e)}",
                )
            )
            all_validations.append(validation)
            if not args.json:
                log(f"  ERROR: {e}", "FAIL")

        if not args.json:
            _print_validation(validation)
            if not validation.passed:
                all_passed = False
                log("  RESULT: FAILED", "FAIL")
            else:
                log("  RESULT: PASSED", "PASS")
            log("")
        elif not validation.passed:
            all_passed = False

    passed_count = sum(1 for v in all_validations if v.passed)
    failed_count = len(all_validations) - passed_count

    if not args.json:
        _print_summary(all_validations, passed_count, failed_count)
    else:
        print(
            json.dumps(
                _json_output(all_validations, passed_count, failed_count),
                indent=2,
                ensure_ascii=False,
            )
        )

    return 0 if all_passed else 1


def _print_validation(validation: PlaybookValidation) -> None:
    for result in validation.results:
        level = "PASS" if result.passed else "FAIL"
        log(f"  {result.check_name}: {result.message}", level)
        if result.details:
            for key, value in result.details.items():
                log(f"    {key}: {value}")


def _print_summary(
    all_validations: List[PlaybookValidation],
    passed_count: int,
    failed_count: int,
) -> None:
    log("=" * 70)
    log("VALIDATION SUMMARY")
    log("=" * 70)

    for validation in all_validations:
        status = "PASS" if validation.passed else "FAIL"
        level = "PASS" if validation.passed else "FAIL"
        log(f"  {validation.capability}/{validation.playbook_code}: {status}", level)

    log("")
    log(
        f"Total: {len(all_validations)}, "
        f"Passed: {passed_count}, Failed: {failed_count}"
    )


def _json_output(
    all_validations: List[PlaybookValidation],
    passed_count: int,
    failed_count: int,
) -> dict:
    return {
        "summary": {
            "total": len(all_validations),
            "passed": passed_count,
            "failed": failed_count,
        },
        "validations": [
            {
                "capability": v.capability,
                "playbook_code": v.playbook_code,
                "passed": v.passed,
                "results": [
                    {
                        "check_name": r.check_name,
                        "passed": r.passed,
                        "message": r.message,
                    }
                    for r in v.results
                ],
            }
            for v in all_validations
        ],
    }
