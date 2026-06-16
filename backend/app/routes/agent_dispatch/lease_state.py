"""Lease ack, progress, and inflight listing helpers."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.app.routes.agent_dispatch.lease_manager")


class LeaseStateMixin:
    """Mixin: lease state transitions for REST polling clients."""

    def ack_task(
        self,
        execution_id: str,
        lease_id: str,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Acknowledge task pickup and extend lease (30s -> 300s).

        Verifies lease_id to prevent ghost duplicate execution.
        Idempotent: re-acking same task+lease returns same result.
        Returns lease info dict or None if rejected.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            if execution_id in self._completed:
                return {"execution_id": execution_id, "status": "already_completed"}
            return None

        if reserved.lease_id != lease_id:
            logger.warning(
                f"[AgentWS] ack lease_id mismatch for {execution_id}: "
                f"expected {reserved.lease_id}, got {lease_id}"
            )
            return None

        if client_id and reserved.client_id != client_id:
            logger.warning(
                f"[AgentWS] ack client mismatch for {execution_id}: "
                f"reserved by {reserved.client_id}, acked by {client_id}"
            )
            return None

        if reserved.acked:
            return {
                "execution_id": execution_id,
                "lease_id": lease_id,
                "lease_expires_at": reserved.lease_deadline,
                "status": "already_acked",
            }

        reserved.acked = True
        reserved.extend_lease(270.0)
        logger.info(f"[AgentWS] Task {execution_id} acked, lease extended to 300s")

        return {
            "execution_id": execution_id,
            "lease_id": lease_id,
            "lease_expires_at": reserved.lease_deadline,
            "status": "acked",
        }

    def report_progress(
        self,
        execution_id: str,
        lease_id: str,
        progress_pct: Optional[float] = None,
        message: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Report task progress and reset lease timer.

        Verifies lease_id. Idempotent: duplicate calls just update timestamp.
        Returns False if lease cap (30min) exceeded.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            return None

        if reserved.lease_id != lease_id:
            return None
        if client_id and reserved.client_id != client_id:
            return None

        if not reserved.reset_lease(120.0):
            logger.warning(
                f"[AgentWS] Lease cap exceeded for {execution_id}, "
                f"cumulative={reserved.cumulative_lease:.0f}s"
            )
            return {
                "execution_id": execution_id,
                "status": "lease_cap_exceeded",
                "cumulative_lease": reserved.cumulative_lease,
            }

        return {
            "execution_id": execution_id,
            "lease_expires_at": reserved.lease_deadline,
            "progress_pct": progress_pct,
            "status": "ok",
        }

    def list_inflight(
        self,
        client_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List tasks currently reserved/inflight for a specific client.

        Used for crash recovery: runner restarts and picks up where it left off.
        """
        self._reclaim_expired_reserves()
        results = []
        for eid, r in self._reserved.items():
            if r.client_id == client_id:
                payload = dict(r.task.payload)
                payload["lease_id"] = r.lease_id
                payload["acked"] = r.acked
                payload["lease_expires_at"] = r.lease_deadline
                results.append(payload)
        return results
