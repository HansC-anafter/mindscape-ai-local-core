"""Interrupted executable composition graph run reconciliation."""

from __future__ import annotations

from backend.app.models.object_runtime import CompositionGraphDiagnostic, CompositionGraphRun
from backend.app.services.object_runtime.composition_graph_run_store import (
    CompositionGraphRunStore,
    utc_iso,
)
from backend.app.services.object_runtime.composition_graph_task_registry import (
    get_graph_run_task,
)

INTERRUPTED_DIAGNOSTIC_CODE = "graph_run_interrupted_by_backend_restart"


def reconcile_interrupted_graph_run(
    *,
    run_store: CompositionGraphRunStore,
    run: CompositionGraphRun,
) -> CompositionGraphRun:
    if run.status not in {"running", "waiting"}:
        return run
    if get_graph_run_task(run.id) is not None:
        return run
    diagnostic = CompositionGraphDiagnostic(
        code=INTERRUPTED_DIAGNOSTIC_CODE,
        message="Composition graph run was interrupted before completion.",
        severity="error",
    )
    return run_store.update_run(
        run.model_copy(
            update={
                "status": "failed",
                "completed_at": utc_iso(),
                "diagnostics": [*run.diagnostics, diagnostic],
            }
        )
    )
