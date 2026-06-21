#!/usr/bin/env python3
"""Compatibility facade for playbook validation."""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_playbooks_lib import (  # noqa: E402
    BASE_URL,
    CAPABILITIES_PATH,
    HAS_REQUESTS,
    HAS_YAML,
    LLM_MOCK,
    OWNER_USER_ID,
    PlaybookValidation,
    PlaybookValidator,
    ValidationResult,
    log,
    main,
)

__all__ = [
    "BASE_URL",
    "CAPABILITIES_PATH",
    "HAS_REQUESTS",
    "HAS_YAML",
    "LLM_MOCK",
    "OWNER_USER_ID",
    "PlaybookValidation",
    "PlaybookValidator",
    "ValidationResult",
    "log",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
