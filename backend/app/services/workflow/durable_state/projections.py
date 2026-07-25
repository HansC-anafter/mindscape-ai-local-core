"""Compact projection construction; persistence remains repository-owned."""

from __future__ import annotations

from .canonical_json import sha256_hex
from .reducers import reduce_v1


def project(state: dict, event: dict) -> tuple[dict, str]:
    updated = reduce_v1(state, event)
    return updated, sha256_hex(updated)
