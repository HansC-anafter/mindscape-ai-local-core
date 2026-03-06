"""
Variant auto-assignment for A/B testing.

When no variant_id is provided by the caller, this module:
1. Lists available variants for the playbook
2. Evaluates variant conditions against execution context
3. Assigns deterministically via hash bucketing
4. Logs the assignment for telemetry
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _evaluate_conditions(
    conditions: Dict[str, Any],
    execution_context: Dict[str, Any],
) -> bool:
    """Check if a variant's conditions match the execution context.

    Supported condition keys:
        locale: exact match against target_language
        risk_level: exact match
        (extensible: add new keys as needed)

    All conditions must match (AND logic). Empty conditions always match.
    """
    if not conditions:
        return True

    for key, expected in conditions.items():
        actual = execution_context.get(key)
        if actual is None:
            return False

        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False

    return True


def _deterministic_bucket(
    workspace_id: str,
    playbook_code: str,
    num_variants: int,
) -> int:
    """Deterministic bucket index via stable hash.

    Same workspace + playbook always gets the same variant,
    ensuring consistent user experience across sessions.
    """
    seed = f"{workspace_id}:{playbook_code}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return int(digest[:8], 16) % num_variants


def assign_variant(
    playbook_code: str,
    variant_id: Optional[str],
    registry,
    workspace_id: Optional[str] = None,
    target_language: Optional[str] = None,
    **extra_context,
) -> Optional[str]:
    """Resolve variant_id for a playbook execution.

    Priority:
    1. Explicit variant_id from caller -> passthrough
    2. Auto-assignment from variants with conditions
    3. None (no variant)

    Args:
        playbook_code: The playbook being executed
        variant_id: Caller-provided variant_id (may be None)
        registry: PlaybookRegistry instance with list_variants()
        workspace_id: For deterministic bucketing
        target_language: Matched against variant conditions.locale
        **extra_context: Additional context for condition evaluation

    Returns:
        Resolved variant_id or None
    """
    # Priority 1: explicit caller override
    if variant_id:
        logger.debug(f"Variant assignment: explicit '{variant_id}' for {playbook_code}")
        return variant_id

    # Priority 2: auto-assignment from conditioned variants
    all_variants = registry.list_variants(playbook_code)
    if not all_variants:
        return None

    # Build execution context for condition matching
    context = {
        "locale": target_language,
        "workspace_id": workspace_id,
        **extra_context,
    }

    # Filter to variants that have conditions and match
    conditioned = []
    for v in all_variants:
        conditions = (
            v.get("conditions")
            if isinstance(v, dict)
            else getattr(v, "conditions", None)
        )
        if conditions:
            if _evaluate_conditions(conditions, context):
                conditioned.append(v)

    if not conditioned:
        return None

    # Single match -> use directly
    if len(conditioned) == 1:
        vid = (
            conditioned[0].get("variant_id")
            if isinstance(conditioned[0], dict)
            else conditioned[0].variant_id
        )
        logger.info(
            f"Variant auto-assigned: '{vid}' for {playbook_code} "
            f"(single condition match)"
        )
        return vid

    # Multiple matches -> deterministic bucket
    if not workspace_id:
        # Without workspace_id, fall back to first match
        vid = (
            conditioned[0].get("variant_id")
            if isinstance(conditioned[0], dict)
            else conditioned[0].variant_id
        )
        logger.info(
            f"Variant auto-assigned: '{vid}' for {playbook_code} "
            f"(first match, no workspace_id for bucketing)"
        )
        return vid

    bucket = _deterministic_bucket(workspace_id, playbook_code, len(conditioned))
    selected = conditioned[bucket]
    vid = (
        selected.get("variant_id")
        if isinstance(selected, dict)
        else selected.variant_id
    )

    logger.info(
        f"Variant auto-assigned: '{vid}' for {playbook_code} "
        f"(bucket {bucket}/{len(conditioned)}, workspace={workspace_id[:8]}...)"
    )
    return vid
