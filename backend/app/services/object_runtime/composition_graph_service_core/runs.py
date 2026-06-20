"""Run scheduling helpers for composition graph service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.app.models.object_runtime import CompositionGraphRun
from backend.app.services.object_runtime.composition_graph_node_registry import (
    build_provider_node_map,
    load_installed_composition_graph_node_providers,
)
from backend.app.services.object_runtime.composition_graph_run_store import (
    CompositionGraphRunStore,
    utc_iso,
)
from backend.app.services.object_runtime.composition_graph_runner import (
    CompositionGraphRunner,
)
from backend.app.services.object_runtime.composition_graph_task_registry import (
    discard_graph_run_task,
    register_graph_run_task,
)


def schedule_graph_run(
    *,
    run: CompositionGraphRun,
    artifacts_store: Any,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]],
    capabilities_dir: Optional[Path],
) -> None:
    task = asyncio.create_task(
        execute_graph_run(
            run=run,
            artifacts_store=artifacts_store,
            local_core_root=local_core_root,
            installed_pack_ids=installed_pack_ids,
            capabilities_dir=capabilities_dir,
        )
    )
    register_graph_run_task(run.id, task)
    task.add_done_callback(lambda _task: discard_graph_run_task(run.id))


async def execute_graph_run(
    *,
    run: CompositionGraphRun,
    artifacts_store: Any,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]],
    capabilities_dir: Optional[Path],
) -> None:
    providers, diagnostics = load_installed_composition_graph_node_providers(
        local_core_root=local_core_root,
        installed_pack_ids=installed_pack_ids,
        capabilities_dir=capabilities_dir,
    )
    run_store = CompositionGraphRunStore(artifacts_store)
    if diagnostics:
        failed = run.model_copy(
            update={
                "status": "failed",
                "completed_at": utc_iso(),
                "diagnostics": [*run.diagnostics, *diagnostics],
            }
        )
        run_store.update_run(failed)
        return
    runner = CompositionGraphRunner(
        run_store=run_store,
        provider_nodes=build_provider_node_map(providers),
    )
    await runner.run(run)
