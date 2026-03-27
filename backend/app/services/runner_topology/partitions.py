"""Canonical queue partitions plus legacy alias compatibility."""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_LOCAL_QUEUE_PARTITION = "default_local"
BROWSER_LOCAL_QUEUE_PARTITION = "browser_local"
VISION_LOCAL_QUEUE_PARTITION = "vision_local"

LEGACY_DEFAULT_QUEUE_PARTITION = "default"
LEGACY_BROWSER_QUEUE_PARTITION = "ig_browser"
LEGACY_VISION_QUEUE_PARTITION = "ig_analysis"

_QUEUE_PARTITION_ALIASES = {
    DEFAULT_LOCAL_QUEUE_PARTITION: (LEGACY_DEFAULT_QUEUE_PARTITION,),
    BROWSER_LOCAL_QUEUE_PARTITION: (LEGACY_BROWSER_QUEUE_PARTITION,),
    VISION_LOCAL_QUEUE_PARTITION: (LEGACY_VISION_QUEUE_PARTITION,),
}

_CANONICAL_QUEUE_PARTITIONS = {
    DEFAULT_LOCAL_QUEUE_PARTITION,
    BROWSER_LOCAL_QUEUE_PARTITION,
    VISION_LOCAL_QUEUE_PARTITION,
}

_LEGACY_TO_CANONICAL = {
    LEGACY_DEFAULT_QUEUE_PARTITION: DEFAULT_LOCAL_QUEUE_PARTITION,
    LEGACY_BROWSER_QUEUE_PARTITION: BROWSER_LOCAL_QUEUE_PARTITION,
    LEGACY_VISION_QUEUE_PARTITION: VISION_LOCAL_QUEUE_PARTITION,
}

_PACK_QUEUE_PARTITIONS = {
    "ig_analyze_pinned_reference": VISION_LOCAL_QUEUE_PARTITION,
    "ig_batch_pin_references": BROWSER_LOCAL_QUEUE_PARTITION,
    "ig_analyze_following": BROWSER_LOCAL_QUEUE_PARTITION,
    "ig_pin_post_detail": BROWSER_LOCAL_QUEUE_PARTITION,
}

RUNNER_READY_QUEUE_ORDER = (
    VISION_LOCAL_QUEUE_PARTITION,
    BROWSER_LOCAL_QUEUE_PARTITION,
    DEFAULT_LOCAL_QUEUE_PARTITION,
)


def normalize_queue_partition(
    value: Any,
    *,
    fallback: Optional[str] = DEFAULT_LOCAL_QUEUE_PARTITION,
) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            if normalized in _CANONICAL_QUEUE_PARTITIONS:
                return normalized
            return _LEGACY_TO_CANONICAL.get(normalized, normalized)
    return fallback


def canonical_queue_partition_for_pack(pack_id: Any) -> str:
    if isinstance(pack_id, str):
        normalized = pack_id.strip()
        if normalized:
            return _PACK_QUEUE_PARTITIONS.get(
                normalized,
                DEFAULT_LOCAL_QUEUE_PARTITION,
            )
    return DEFAULT_LOCAL_QUEUE_PARTITION


def queue_partition_aliases(value: Any) -> tuple[str, ...]:
    canonical = normalize_queue_partition(value, fallback=None)
    if canonical is None:
        return ()
    aliases = [canonical]
    aliases.extend(_QUEUE_PARTITION_ALIASES.get(canonical, ()))
    return tuple(aliases)


def queue_partition_matches(candidate: Any, expected: Any) -> bool:
    return normalize_queue_partition(candidate) == normalize_queue_partition(expected)


def queue_partition_env_suffixes(value: Any) -> tuple[str, ...]:
    return tuple(
        token.upper().replace("-", "_")
        for token in queue_partition_aliases(value)
    )


def build_queue_partition_filter_clause(
    column_sql: str,
    queue_partition: Any,
    *,
    param_prefix: str = "queue_partition",
) -> tuple[str, dict[str, str]]:
    aliases = queue_partition_aliases(queue_partition)
    if not aliases:
        return "", {}

    placeholders: list[str] = []
    params: dict[str, str] = {}
    for index, token in enumerate(aliases):
        key = f"{param_prefix}_{index}"
        params[key] = token
        placeholders.append(f":{key}")

    default_key = f"{param_prefix}_default"
    params[default_key] = LEGACY_DEFAULT_QUEUE_PARTITION
    clause = (
        f"COALESCE({column_sql}, :{default_key}) IN ({', '.join(placeholders)})"
    )
    return clause, params
