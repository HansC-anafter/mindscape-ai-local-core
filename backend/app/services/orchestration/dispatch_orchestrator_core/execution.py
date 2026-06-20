"""DAG execution loop helpers for DispatchOrchestrator."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from backend.app.models.task_ir import PhaseIR, PhaseStatus, TaskIR

logger = logging.getLogger(__name__)


async def execute_task_ir(
    orchestrator: Any,
    task_ir: Optional[TaskIR],
    action_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Walk the TaskIR DAG and dispatch all phases through the facade instance."""
    if not task_ir or not task_ir.phases:
        return {"status": "empty", "total": 0, "succeeded": 0, "failed": 0}

    phases = task_ir.phases
    orchestrator._normalize_phase_inputs(phases, action_items)

    await orchestrator._publish_activity(
        "dispatch_started",
        {
            "task_ir_id": task_ir.task_id,
            "total_phases": len(phases),
        },
    )
    phase_map: Dict[str, PhaseIR] = {p.id: p for p in phases}

    dependents: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {p.id: 0 for p in phases}
    for phase in phases:
        for dep_id in phase.depends_on or []:
            if dep_id in phase_map:
                dependents[dep_id].append(phase.id)
                in_degree[phase.id] += 1

    ready: List[str] = [pid for pid, deg in in_degree.items() if deg == 0]
    completed_phases: Set[str] = set()
    failed_phases: Set[str] = set()
    skipped_phases: Set[str] = set()
    workspaces: Set[str] = set()

    items_by_title: Dict[str, Dict[str, Any]] = {}
    for item in action_items:
        title = item.get("title", "")
        if title:
            items_by_title[title] = item

    while ready:
        dispatch_tasks = []
        for pid in ready:
            phase = phase_map[pid]
            item = items_by_title.get(phase.name, {})
            dispatch_tasks.append(
                orchestrator._dispatch_phase(phase, item, task_ir.task_id)
            )

        results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)

        next_ready: List[str] = []
        for pid, result in zip(ready, results):
            phase = phase_map[pid]
            if isinstance(result, Exception):
                logger.warning("Phase %s dispatch raised exception: %s", pid, result)
                failed_phases.add(pid)
                phase.status = PhaseStatus.FAILED
            elif result.get("status") == "completed":
                completed_phases.add(pid)
                phase.status = PhaseStatus.COMPLETED
                phase_result = result.get("result")
                if isinstance(phase_result, dict):
                    orchestrator._phase_results[pid] = phase_result
                ws = result.get("workspace_id")
                if ws:
                    workspaces.add(ws)
            elif result.get("status") == "skipped":
                skipped_phases.add(pid)
                phase.status = PhaseStatus.SKIPPED
            else:
                failed_phases.add(pid)
                phase.status = PhaseStatus.FAILED

            for dep_pid in dependents.get(pid, []):
                in_degree[dep_pid] -= 1
                if in_degree[dep_pid] == 0:
                    if orchestrator._should_skip(dep_pid, phase_map):
                        skipped_phases.add(dep_pid)
                        phase_map[dep_pid].status = PhaseStatus.SKIPPED
                        attempt = orchestrator._create_attempt(
                            phase_map[dep_pid], task_ir.task_id
                        )
                        attempt.mark_skipped("upstream_dependency_failed")
                        for sub_dep in dependents.get(dep_pid, []):
                            in_degree[sub_dep] -= 1
                            if in_degree[sub_dep] == 0:
                                next_ready.append(sub_dep)
                    else:
                        next_ready.append(dep_pid)

        ready = next_ready

        if orchestrator._on_wave_complete and ready:
            try:
                wave_summary = {
                    "completed": sorted(completed_phases),
                    "failed": sorted(failed_phases),
                    "skipped": sorted(skipped_phases),
                    "phase_results": dict(orchestrator._phase_results),
                }
                new_phases = await orchestrator._on_wave_complete(
                    wave_summary, task_ir
                )
                if new_phases:
                    for new_phase in new_phases:
                        if new_phase.id not in phase_map:
                            task_ir.phases.append(new_phase)
                            phase_map[new_phase.id] = new_phase
                            in_degree[new_phase.id] = 0
                            for dep_id in new_phase.depends_on or []:
                                if dep_id in phase_map:
                                    dependents[dep_id].append(new_phase.id)
                                    in_degree[new_phase.id] += 1
                            if in_degree[new_phase.id] == 0:
                                ready.append(new_phase.id)
                    logger.info("Supervisor injected %d new phases", len(new_phases))
            except Exception as exc:
                logger.warning("Supervisor callback failed (non-fatal): %s", exc)

    total = len(phases)
    succeeded = len(completed_phases)
    failed = len(failed_phases)
    skipped = len(skipped_phases)

    if failed == 0 and skipped == 0:
        agg_status = "ok"
    elif succeeded == 0:
        agg_status = "all_failed"
    else:
        agg_status = "partial_failure"

    session_id = getattr(orchestrator.session, "id", None)
    if orchestrator.tasks_store and orchestrator._attempts and session_id:
        try:
            store_attempts = getattr(orchestrator.tasks_store, "store_phase_attempts", None)
            if store_attempts:
                store_attempts(
                    session_id=session_id,
                    attempts=[
                        att.model_dump(mode="json")
                        for att in orchestrator._attempts.values()
                    ],
                )
            else:
                from backend.app.services.stores.meeting_session_store import (
                    MeetingSessionStore,
                )

                try:
                    ss = MeetingSessionStore()
                    session_obj = ss.get_by_id(session_id)
                    if session_obj:
                        session_obj.metadata["phase_attempts"] = {
                            pid: att.model_dump(mode="json")
                            for pid, att in orchestrator._attempts.items()
                        }
                        ss.update(session_obj)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Attempt persistence failed (non-fatal): %s", exc)

    await orchestrator._publish_activity(
        "dispatch_completed",
        {
            "task_ir_id": task_ir.task_id,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )

    return {
        "status": agg_status,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "workspaces": sorted(workspaces),
        "attempts": {
            pid: att.model_dump(mode="json")
            for pid, att in orchestrator._attempts.items()
        },
        "phase_results": [
            {
                "phase_id": pid,
                "status": (
                    "completed"
                    if pid in completed_phases
                    else ("failed" if pid in failed_phases else "skipped")
                ),
            }
            for pid in phase_map
        ],
    }
