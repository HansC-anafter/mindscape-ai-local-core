"""Injected-store persistence helpers for MCP event hooks."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from .contracts import utc_now

logger = logging.getLogger("backend.app.services.mcp_event_hooks")


async def run_idempotent(
    service: Any,
    idem_key: str,
    hook_type: str,
    workspace_id: str,
    fn: Callable,
    **kwargs: Any,
) -> Any:
    """Run a hook function once per idempotency key."""
    existing = await service._get_hook_run(idem_key)
    if existing:
        logger.info(
            "Idempotent skip: %s already executed (key=%s...)",
            hook_type,
            idem_key[:16],
        )
        return existing.get("result_summary")

    try:
        result = await fn(**kwargs)
        await service._record_hook_run(
            idem_key=idem_key,
            hook_type=hook_type,
            workspace_id=workspace_id,
            status="completed",
            result_summary=result,
        )
        return result
    except Exception as exc:
        logger.error("Hook %s failed: %s", hook_type, exc, exc_info=True)
        await service._record_hook_run(
            idem_key=idem_key,
            hook_type=hook_type,
            workspace_id=workspace_id,
            status="failed",
            result_summary={"error": str(exc)},
        )
        return None


def build_key(workspace_id: str, message_id: str, step: str) -> str:
    """Build deterministic idempotency key."""
    raw = f"{workspace_id}:{message_id}:{step}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


async def emit(
    service: Any,
    event_type: str,
    source: str,
    workspace_id: str,
    trace_id: str,
    payload: Dict[str, Any],
) -> str:
    """Emit an MCP event through the injected store when available."""
    event_id = str(uuid.uuid4())
    try:
        if service.store and hasattr(service.store, "execute_raw"):
            await service.store.execute_raw(
                """INSERT INTO mcp_events
                   (event_id, event_type, source, workspace_id,
                    idempotency_key, trace_id, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    event_type,
                    source,
                    workspace_id,
                    f"{event_type}:{trace_id}",
                    trace_id,
                    str(payload),
                    utc_now().isoformat(),
                ),
            )
        else:
            logger.info(
                "MCP Event [%s] source=%s ws=%s trace=%s payload=%s",
                event_type,
                source,
                workspace_id,
                trace_id,
                payload,
            )
    except Exception as exc:
        logger.warning("Failed to emit MCP event: %s", exc)

    return event_id


async def get_hook_run(service: Any, idem_key: str) -> Optional[Dict[str, Any]]:
    """Check if a hook run already exists."""
    try:
        if service.store and hasattr(service.store, "execute_raw"):
            row = await service.store.execute_raw(
                "SELECT * FROM mcp_hook_runs WHERE idempotency_key = ?",
                (idem_key,),
            )
            if row:
                return row[0] if isinstance(row, list) else row
    except Exception:
        pass

    return None


async def record_hook_run(
    service: Any,
    idem_key: str,
    hook_type: str,
    workspace_id: str,
    status: str,
    result_summary: Any,
) -> None:
    """Record a hook run for idempotency."""
    try:
        if service.store and hasattr(service.store, "execute_raw"):
            await service.store.execute_raw(
                """INSERT INTO mcp_hook_runs
                   (idempotency_key, hook_type, workspace_id,
                    status, result_summary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (idempotency_key) DO NOTHING""",
                (
                    idem_key,
                    hook_type,
                    workspace_id,
                    status,
                    str(result_summary),
                    utc_now().isoformat(),
                ),
            )
        else:
            logger.info(
                "MCP Hook Run [%s] key=%s... status=%s",
                hook_type,
                idem_key[:16],
                status,
            )
    except Exception as exc:
        logger.warning("Failed to record hook run: %s", exc)
