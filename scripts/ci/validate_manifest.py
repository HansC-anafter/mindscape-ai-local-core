#!/usr/bin/env python3
"""
CI Script: Validate Manifest Schema

Validates capability manifest.yaml against schema.

Requirements:
- portability field (required)
- environments must include local-core
- tool backend must use capabilities.* format (mindscape.capabilities.* is deprecated)
- API path must be under api/ directory

Usage:
    python scripts/ci/validate_manifest.py capabilities/
    python scripts/ci/validate_manifest.py --strict capabilities/example_capability
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_manifest_lib import (  # noqa: E402
    ValidationError,
    ValidationResult,
    _validate_runtime_read_path_budgets,
    format_results,
    main,
    validate_directory,
    validate_manifest,
)

__all__ = [
    "ValidationError",
    "ValidationResult",
    "validate_manifest",
    "validate_directory",
    "format_results",
    "main",
    "_validate_runtime_read_path_budgets",
]


if __name__ == "__main__":
    main()
