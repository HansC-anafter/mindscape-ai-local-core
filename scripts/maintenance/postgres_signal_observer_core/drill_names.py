"""Single canonical name derivation seam for the disposable observer drill."""

from __future__ import annotations

import re


DRILL_SUFFIX_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
DISPOSABLE_DRILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")

_PREFIXES = {
    "network": "runtime-db-observer-drill",
    "postgres": "runtime-db-observer-drill-postgres",
    "pgbouncer": "runtime-db-observer-drill-pgbouncer",
    "observer": "runtime-db-observer-drill-observer",
    "client": "runtime-db-observer-drill-client",
}


def normalize_disposable_drill_suffix(drill_suffix: str) -> str:
    """Validate the exact UTC suffix and lowercase only its fixed separators."""

    candidate = str(drill_suffix)
    if not DRILL_SUFFIX_PATTERN.fullmatch(candidate):
        raise ValueError("disposable_drill_suffix_invalid")
    return candidate.lower()


def validate_disposable_drill_name(value: str) -> str:
    """Return one exact lowercase Docker name or fail closed."""

    candidate = str(value)
    if not DISPOSABLE_DRILL_NAME_PATTERN.fullmatch(candidate):
        raise ValueError("disposable_drill_name_invalid")
    return candidate


def canonical_disposable_drill_name(role: str, drill_suffix: str) -> str:
    """Derive one deterministic role name without a hash or fallback branch."""

    prefix = _PREFIXES.get(str(role))
    if prefix is None:
        raise ValueError("disposable_drill_name_role_invalid")
    return validate_disposable_drill_name(
        f"{prefix}-{normalize_disposable_drill_suffix(drill_suffix)}"
    )
