"""Reference analysis concurrency repair helpers."""

from __future__ import annotations

from typing import Any, Optional

REFERENCE_ANALYSIS_PACK_ID = "ig_analyze_pinned_reference"


def _string_value(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def reference_id_from_context(ctx: dict[str, Any]) -> Optional[str]:
    inputs = ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {}
    return _string_value(inputs.get("reference_id"))


def per_reference_concurrency_key(pack_id: str, reference_id: str) -> str:
    return f"concurrency:playbook_input:{pack_id}:{reference_id}"


def normalize_reference_analysis_concurrency(
    *,
    pack_id: Any,
    ctx: dict[str, Any],
) -> tuple[dict[str, Any], Optional[str]]:
    if str(pack_id or "").strip() != REFERENCE_ANALYSIS_PACK_ID:
        return ctx, None
    reference_id = reference_id_from_context(ctx)
    if not reference_id:
        return ctx, None

    concurrency = ctx.get("concurrency")
    expected_concurrency = {
        "lock_scope": "playbook_input",
        "lock_key_input": "reference_id",
        "max_parallel": 1,
    }
    expected_key = per_reference_concurrency_key(REFERENCE_ANALYSIS_PACK_ID, reference_id)
    if concurrency == expected_concurrency:
        return ctx, expected_key

    ctx2 = dict(ctx)
    ctx2["concurrency"] = expected_concurrency
    return ctx2, expected_key
