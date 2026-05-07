"""Helpers for JSON text that must stay compatible with PostgreSQL text/jsonb."""

import json
from typing import Any

JSON_NUL_REPLACEMENT = "\ufffd"


def replace_json_nul_codepoints(value: Any) -> Any:
    """Replace real NUL codepoints after JSON parsing without touching literal \\u0000 text."""
    if isinstance(value, str):
        return value.replace("\x00", JSON_NUL_REPLACEMENT)
    if isinstance(value, list):
        return [replace_json_nul_codepoints(item) for item in value]
    if isinstance(value, dict):
        return {
            replace_json_nul_codepoints(key): replace_json_nul_codepoints(item)
            for key, item in value.items()
        }
    return value


def json_value_without_nul(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return replace_json_nul_codepoints(value)
    if isinstance(value, str):
        try:
            return replace_json_nul_codepoints(json.loads(value))
        except Exception:
            return default
    return default
