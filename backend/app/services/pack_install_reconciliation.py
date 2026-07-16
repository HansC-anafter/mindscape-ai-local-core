"""Public facade for durable committed-pack reconciliation."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from backend.app.services.pack_install_reconciliation_core.reconciler import (
    CommittedInstallReconciler,
)
from backend.app.services.pack_install_reconciliation_core.store import (
    PackInstallReconciliationStore,
)


_CLEAN_POLL_INTERVAL_SECONDS = 30.0
_clean_until_monotonic = 0.0
_poll_lock = threading.Lock()


def record_projection_result(
    install_id: str,
    *,
    succeeded: bool,
    error: Optional[str] = None,
) -> None:
    PackInstallReconciliationStore().mark_projection(
        install_id,
        succeeded=succeeded,
        error=error,
    )


def record_filesystem_cleanup_result(
    install_id: str,
    *,
    succeeded: bool,
    error: Optional[str] = None,
) -> None:
    PackInstallReconciliationStore().mark_filesystem_cleanup(
        install_id,
        succeeded=succeeded,
        error=error,
    )


def reconcile_install_truth_once() -> Optional[dict[str, Any]]:
    return CommittedInstallReconciler().reconcile_next()


def has_incomplete_install_reconciliation() -> bool:
    return CommittedInstallReconciler().has_incomplete()


def poll_install_reconciliation_once() -> Optional[dict[str, Any]]:
    """Poll durable reconciliation without adding a DB query every worker tick.

    A clean result is cached for 30 seconds. The job claim statement separately
    rejects claims while any incomplete receipt exists, so another process cannot
    bypass reconciliation during this local clean-cache window.
    """

    global _clean_until_monotonic
    with _poll_lock:
        now = time.monotonic()
        if now < _clean_until_monotonic:
            return None
        reconciler = CommittedInstallReconciler()
        result = reconciler.reconcile_next()
        if result is not None:
            _clean_until_monotonic = 0.0
            return result
        if reconciler.has_incomplete():
            return {
                "kind": "pack_install_reconciliation",
                "ok": False,
                "state": "waiting_retry_window",
                "retry_after_seconds": 30,
            }
        _clean_until_monotonic = now + _CLEAN_POLL_INTERVAL_SECONDS
        return None


__all__ = [
    "CommittedInstallReconciler",
    "PackInstallReconciliationStore",
    "has_incomplete_install_reconciliation",
    "poll_install_reconciliation_once",
    "reconcile_install_truth_once",
    "record_filesystem_cleanup_result",
    "record_projection_result",
]
