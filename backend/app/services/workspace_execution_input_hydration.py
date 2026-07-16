"""Facade-only bounded execution input hydration for compact run logs."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from backend.app.services.task_projection_adapters import (
    load_task_display_input_overlays,
)


def hydrate_missing_execution_inputs(
    conn,
    rows: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Delegate exact selected task IDs without owning any pack input keys."""

    return load_task_display_input_overlays(conn=conn, rows=list(rows))
