"""Policy gate finding mutation helpers."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _mark_blocked(
    item: Dict[str, Any],
    reason_code: str,
    message: str,
) -> None:
    """Mark an action item as policy-blocked."""
    item["landing_status"] = "policy_blocked"
    item["landing_error"] = message
    item["policy_reason_code"] = reason_code
    logger.info(
        "Policy gate blocked item '%s': %s (%s)",
        item.get("title"),
        message,
        reason_code,
    )


def _apply_block(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Apply an unconditional block finding to item and report."""
    _add_block_detail(item, detail, item_report)
    _mark_blocked(
        item,
        reason_code=detail["reason_code"],
        message=detail["message"],
    )
    item_report["status"] = item.get("landing_status") or "policy_blocked"
    _update_item_policy_gate(item, item_report)


def _add_warning(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Attach a machine-readable warning to item and report."""
    warning = dict(detail)
    warning["policy_warning_code"] = warning["reason_code"]
    warnings = item.setdefault("policy_warnings", [])
    warnings.append(warning)
    item["policy_warning"] = warnings[0]
    item_report["warnings"].append(warning)
    logger.info(
        "Policy gate warning on item '%s': %s (%s)",
        item.get("title"),
        warning["message"],
        warning["reason_code"],
    )


def _add_block_detail(
    item: Dict[str, Any],
    detail: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Attach a machine-readable block detail to item and report."""
    block = dict(detail)
    block["policy_reason_code"] = block["reason_code"]
    item.setdefault("policy_blocks", []).append(block)
    item_report["blocks"].append(block)


def _update_item_policy_gate(
    item: Dict[str, Any],
    item_report: Dict[str, Any],
) -> None:
    """Write normalized policy gate metadata back to action item."""
    item["policy_gate"] = {
        "requested_mode": item_report["requested_mode"],
        "effective_mode": item_report["effective_mode"],
        "mode_source": item_report["mode_source"],
        "status": item_report["status"],
        "warnings": list(item_report["warnings"]),
        "blocks": list(item_report["blocks"]),
        "auto_filled_governance_fields": list(
            item_report.get("auto_filled_governance_fields", [])
        ),
    }


def _build_policy_detail(
    *,
    reason_code: str,
    message: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Create a normalized machine-readable policy finding payload."""
    detail = {
        "reason_code": reason_code,
        "message": message,
    }
    detail.update(extra)
    return detail
