"""Receipt validation helpers for MCP event hooks."""

from __future__ import annotations

import logging
import re
from datetime import datetime as dt
from typing import Any, Dict, List

from .contracts import ReceiptDecision, utc_now

logger = logging.getLogger("backend.app.services.mcp_event_hooks")

_HASH_RE = re.compile(r"^[0-9a-fA-F]{16,64}$")


def evaluate_receipt(step: str, receipts: List[Dict[str, Any]]) -> ReceiptDecision:
    """
    Evaluate an IDE receipt for a given hook step.

    The accepted receipt path preserves the existing receipts-over-claims
    behavior: accepted receipts skip hook execution; invalid or missing
    receipts keep the hook runnable.
    """
    receipt = next((item for item in receipts if item.get("step") == step), None)

    if not receipt:
        return ReceiptDecision(
            step=step,
            should_run=True,
            reason="no_receipt",
        )

    trace_id = receipt.get("trace_id", "")
    output_hash = receipt.get("output_hash", "")

    if not trace_id:
        logger.warning("Receipt for %s: missing trace_id", step)
        return ReceiptDecision(
            step=step,
            should_run=True,
            reason="missing_trace_id",
            receipt_trace_id=trace_id,
            receipt_output_hash=output_hash,
        )

    if not output_hash or not _HASH_RE.match(output_hash):
        logger.warning(
            "Receipt for %s: invalid output_hash (got '%s...' - expected hex >=16 chars)",
            step,
            output_hash[:20],
        )
        return ReceiptDecision(
            step=step,
            should_run=True,
            reason="invalid_output_hash",
            receipt_trace_id=trace_id,
            receipt_output_hash=output_hash,
        )

    completed_at = receipt.get("completed_at")
    if completed_at:
        try:
            timestamp = dt.fromisoformat(completed_at.replace("Z", "+00:00"))
            if timestamp > utc_now():
                logger.warning("Receipt for %s: completed_at is in the future", step)
                return ReceiptDecision(
                    step=step,
                    should_run=True,
                    reason="future_completed_at",
                    receipt_trace_id=trace_id,
                    receipt_output_hash=output_hash,
                )
        except (ValueError, TypeError):
            logger.debug("Receipt for %s: unparsable completed_at", step)

    return ReceiptDecision(
        step=step,
        should_run=False,
        reason="receipt_accepted",
        receipt_trace_id=trace_id,
        receipt_output_hash=output_hash,
    )


def should_run_hook(step: str, receipts: List[Dict[str, Any]]) -> bool:
    return evaluate_receipt(step, receipts).should_run


async def emit_receipt_audit(
    service: Any,
    decision: ReceiptDecision,
    workspace_id: str,
    trace_id: str,
) -> None:
    """Emit a receipt audit event for accepted or rejected receipts."""
    if decision.reason == "no_receipt":
        return

    event_type = "receipt_accepted" if not decision.should_run else "receipt_rejected"
    await service._emit(
        event_type=event_type,
        source="receipt_validator",
        workspace_id=workspace_id,
        trace_id=trace_id,
        payload={
            "step": decision.step,
            "reason": decision.reason,
            "receipt_trace_id": decision.receipt_trace_id,
            "receipt_hash_prefix": (
                decision.receipt_output_hash[:8]
                if decision.receipt_output_hash
                else None
            ),
        },
    )
