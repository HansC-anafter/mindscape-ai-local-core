"""Shared IG source-context filters for confirmed targets."""

from typing import Optional

CONFIRMED_SOURCE_CONTEXT = "following_list"
UNVERIFIED_SOURCE_CONTEXTS = frozenset({"suggestion", "unknown"})
RISK_CONTROLLED_STOP_REASONS = frozenset({"blocked", "risk_control_suspected"})


def confirmed_target_condition_sql(alias: str = "") -> str:
    """Return the SQL predicate for confirmed saved targets."""
    prefix = f"{alias}." if alias else ""
    return (
        f"COALESCE(NULLIF({prefix}source_context, ''), '{CONFIRMED_SOURCE_CONTEXT}') = "
        f"'{CONFIRMED_SOURCE_CONTEXT}' AND {prefix}handle NOT LIKE '__seed_placeholder__%'"
    )


def should_persist_source_pool(
    source_context: Optional[str],
    stop_reason: Optional[str] = None,
) -> bool:
    """Decide whether non-primary pools should be persisted into ig_accounts_flat."""
    normalized_source = (source_context or "").strip().lower()
    normalized_stop_reason = (stop_reason or "").strip().lower()

    if not normalized_source or normalized_source == CONFIRMED_SOURCE_CONTEXT:
        return True
    if normalized_source == "suggestion":
        return False
    if (
        normalized_source == "unknown"
        and normalized_stop_reason in RISK_CONTROLLED_STOP_REASONS
    ):
        return False
    return normalized_source not in UNVERIFIED_SOURCE_CONTEXTS or normalized_source == "unknown"
