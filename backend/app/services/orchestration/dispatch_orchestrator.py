"""
DispatchOrchestrator — DAG walker with dependency gating.

Replaces BridgeDispatcher (Phase 1) with a proper DAG-walking dispatcher
that tracks PhaseAttempts, respects dependency ordering, and writes
projection records for backward-compatible task queries.

Design:
  1. Build dependency graph from PhaseIR.depends_on
  2. Topological walk: dispatch ready phases (all deps completed)
  3. Dependency gate: if upstream FAILED → downstream SKIPPED
  4. Per-phase PhaseAttempt lifecycle tracking
  5. Projection: update legacy tasks store for API consumers
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from backend.app.models.phase_attempt import (
    AttemptStatus,
    PhaseAttempt,
)
from backend.app.models.task_ir import PhaseIR, PhaseStatus, TaskIR

logger = logging.getLogger(__name__)


class DispatchOrchestrator:
    """DAG-walking dispatch orchestrator.

    Accepts a compiled TaskIR and walks its phase graph, dispatching
    phases whose dependencies are satisfied. Tracks each dispatch as
    a PhaseAttempt for audit and retry.

    Args:
        execution_launcher: Callable for playbook/task dispatch (may be None).
        tasks_store: Legacy tasks store for projection writes.
        session: MeetingSession providing routing defaults.
        profile_id: Current user profile.
        project_id: Current project (may be None).
        skip_policy: 'skip_on_dep_failure' (default) or 'continue_on_dep_failure'.
    """

    def __init__(
        self,
        execution_launcher: Any = None,
        tasks_store: Any = None,
        session: Any = None,
        profile_id: str = "",
        project_id: Optional[str] = None,
        skip_policy: str = "skip_on_dep_failure",
    ):
        self.execution_launcher = execution_launcher
        self.tasks_store = tasks_store
        self.session = session
        self.profile_id = profile_id
        self.project_id = project_id
        self.skip_policy = skip_policy

        # PhaseAttempt tracking (phase_id → latest attempt)
        self._attempts: Dict[str, PhaseAttempt] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        task_ir: Optional[TaskIR],
        action_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Walk the TaskIR DAG and dispatch all phases.

        Returns:
            Dict with dispatch summary (status, total, succeeded, failed,
            skipped, workspaces, attempts).
        """
        if not task_ir or not task_ir.phases:
            return {"status": "empty", "total": 0, "succeeded": 0, "failed": 0}

        phases = task_ir.phases
        phase_map: Dict[str, PhaseIR] = {p.id: p for p in phases}

        # Build adjacency + in-degree for topo walk
        dependents: Dict[str, List[str]] = defaultdict(list)  # dep → [downstream]
        in_degree: Dict[str, int] = {p.id: 0 for p in phases}
        for p in phases:
            for dep_id in p.depends_on or []:
                if dep_id in phase_map:
                    dependents[dep_id].append(p.id)
                    in_degree[p.id] += 1

        # Identify ready phases (in_degree == 0)
        ready: List[str] = [pid for pid, deg in in_degree.items() if deg == 0]
        completed_phases: Set[str] = set()
        failed_phases: Set[str] = set()
        skipped_phases: Set[str] = set()
        workspaces: Set[str] = set()

        # Build action_items lookup by title for projection
        items_by_title: Dict[str, Dict[str, Any]] = {}
        for item in action_items:
            title = item.get("title", "")
            if title:
                items_by_title[title] = item

        # Wave-based DAG walk
        while ready:
            # Dispatch all ready phases concurrently
            dispatch_tasks = []
            for pid in ready:
                phase = phase_map[pid]
                item = items_by_title.get(phase.name, {})
                dispatch_tasks.append(
                    self._dispatch_phase(phase, item, task_ir.task_id)
                )

            results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)

            # Process results and unlock downstream
            next_ready: List[str] = []
            for pid, result in zip(ready, results):
                phase = phase_map[pid]
                if isinstance(result, Exception):
                    logger.warning(
                        "Phase %s dispatch raised exception: %s", pid, result
                    )
                    failed_phases.add(pid)
                    phase.status = PhaseStatus.FAILED
                elif result.get("status") == "completed":
                    completed_phases.add(pid)
                    phase.status = PhaseStatus.COMPLETED
                    ws = result.get("workspace_id")
                    if ws:
                        workspaces.add(ws)
                elif result.get("status") == "skipped":
                    skipped_phases.add(pid)
                    phase.status = PhaseStatus.SKIPPED
                else:
                    failed_phases.add(pid)
                    phase.status = PhaseStatus.FAILED

                # Unlock dependents
                for dep_pid in dependents.get(pid, []):
                    in_degree[dep_pid] -= 1
                    if in_degree[dep_pid] == 0:
                        # Check dependency gate
                        if self._should_skip(dep_pid, phase_map):
                            skipped_phases.add(dep_pid)
                            phase_map[dep_pid].status = PhaseStatus.SKIPPED
                            attempt = self._create_attempt(
                                phase_map[dep_pid], task_ir.task_id
                            )
                            attempt.mark_skipped("upstream_dependency_failed")
                            # Continue unlocking downstream of skipped
                            for sub_dep in dependents.get(dep_pid, []):
                                in_degree[sub_dep] -= 1
                                if in_degree[sub_dep] == 0:
                                    next_ready.append(sub_dep)
                        else:
                            next_ready.append(dep_pid)

            ready = next_ready

        # Aggregate
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

        # Persist PhaseAttempt records to tasks_store for L5→L3 signal path
        session_id = getattr(self.session, "id", None)
        if self.tasks_store and self._attempts and session_id:
            try:
                store_attempts = getattr(self.tasks_store, "store_phase_attempts", None)
                if store_attempts:
                    store_attempts(
                        session_id=session_id,
                        attempts=[
                            att.model_dump(mode="json")
                            for att in self._attempts.values()
                        ],
                    )
                else:
                    # Fallback: store as session metadata via meeting session store
                    from backend.app.services.stores.meeting_session_store import (
                        MeetingSessionStore,
                    )

                    try:
                        ss = MeetingSessionStore()
                        session_obj = ss.get_by_id(session_id)
                        if session_obj:
                            session_obj.metadata["phase_attempts"] = {
                                pid: att.model_dump(mode="json")
                                for pid, att in self._attempts.items()
                            }
                            ss.update(session_obj)
                    except Exception:
                        pass  # non-fatal
            except Exception as exc:
                logger.warning("Attempt persistence failed (non-fatal): %s", exc)

        return {
            "status": agg_status,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "workspaces": sorted(workspaces),
            "attempts": {
                pid: att.model_dump(mode="json") for pid, att in self._attempts.items()
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

    # ------------------------------------------------------------------
    # Phase dispatch
    # ------------------------------------------------------------------

    async def _dispatch_phase(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        task_ir_id: str,
    ) -> Dict[str, Any]:
        """Dispatch a single phase, creating a PhaseAttempt."""
        attempt = self._create_attempt(phase, task_ir_id)

        # Check if action_item is pre-blocked (policy gate)
        landing_status = action_item.get("landing_status", "")
        if landing_status in ("policy_blocked", "dispatch_error", "boundary_violation"):
            attempt.mark_skipped(f"pre_blocked:{landing_status}")
            return {"status": "skipped", "reason": landing_status}

        # Resolve target workspace
        target_ws = (
            phase.target_workspace_id
            or action_item.get("target_workspace_id")
            or getattr(self.session, "workspace_id", None)
            or ""
        )

        # Resolve engine/adapter
        engine = phase.preferred_engine or "playbook:generic"
        playbook_code = self._extract_playbook_code(engine)

        # Mark dispatched
        attempt.mark_dispatched(
            engine=engine,
            playbook_code=playbook_code,
            target_workspace_id=target_ws,
        )

        # Execute dispatch
        try:
            if playbook_code and self.execution_launcher:
                # Playbook dispatch path
                result = await self._launch_playbook(
                    playbook_code=playbook_code,
                    action_item=action_item,
                    target_workspace_id=target_ws,
                    attempt=attempt,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "launched"
                return {
                    "status": "completed",
                    "workspace_id": target_ws,
                    "result": result,
                }
            elif phase.tool_name:
                # Tool execution path
                result = await self._dispatch_tool(
                    phase=phase,
                    action_item=action_item,
                    target_workspace_id=target_ws,
                    attempt=attempt,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "task_created"
                return {
                    "status": "completed",
                    "workspace_id": target_ws,
                    "result": result,
                }
            else:
                # Fallback: create task projection
                result = self._project_to_task(
                    phase=phase,
                    action_item=action_item,
                    target_workspace_id=target_ws,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "planned"
                return {
                    "status": "completed",
                    "workspace_id": target_ws,
                    "result": result,
                }
        except Exception as exc:
            error_msg = str(exc)
            attempt.mark_failed(error_msg)
            action_item["landing_status"] = "dispatch_error"
            action_item["landing_error"] = error_msg
            logger.warning("Phase %s dispatch failed: %s", phase.id, exc)
            return {"status": "failed", "error": error_msg}

    # ------------------------------------------------------------------
    # Adapter methods
    # ------------------------------------------------------------------

    async def _launch_playbook(
        self,
        playbook_code: str,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
    ) -> Dict[str, Any]:
        """Launch a playbook via execution_launcher.

        Matches the proven contract from _land_action_item:
        - inputs: meeting context dict (task, meeting_session_id, thread_id, workspace_id)
        - ctx: LocalDomainContext with actor_id + workspace_id
        - trace_id: unique per dispatch for tracking
        - session metadata: appends execution_id to session.metadata["execution_ids"]
        """
        import uuid as _uuid

        from backend.app.core.domain_context import LocalDomainContext

        attempt.mark_started()

        # Build inputs dict matching _land_action_item semantics
        inputs = {
            "task": action_item.get("description", ""),
            "meeting_session_id": getattr(self.session, "id", None),
            "thread_id": getattr(self.session, "thread_id", None),
            "workspace_id": target_workspace_id,
        }
        # Inject full lineage chain for L4 transport correlation
        inputs["phase_attempt_id"] = attempt.id
        inputs["phase_id"] = attempt.phase_id
        inputs["task_ir_id"] = attempt.task_ir_id

        # Merge any explicit input_params from TaskIR phase
        extra_params = action_item.get("input_params")
        if isinstance(extra_params, dict):
            inputs.update(extra_params)

        ctx = LocalDomainContext(
            actor_id=self.profile_id,
            workspace_id=target_workspace_id,
        )

        try:
            result = await self.execution_launcher.launch(
                playbook_code=playbook_code,
                inputs=inputs,
                ctx=ctx,
                project_id=self.project_id,
                trace_id=str(_uuid.uuid4()),
            )

            execution_id = result.get("execution_id")

            # Write execution_id back to attempt.adapter_meta
            # for direct attempt → execution_id join
            if execution_id:
                attempt.adapter_meta["execution_id"] = execution_id

            # Track execution_id in session metadata (matches _land_action_item)
            if execution_id and self.session:
                exec_ids = self.session.metadata.setdefault("execution_ids", [])
                if execution_id not in exec_ids:
                    exec_ids.append(execution_id)

            return {
                "execution_id": execution_id,
                "playbook_code": playbook_code,
                "phase_id": attempt.phase_id,
                "attempt_id": attempt.id,
            }
        except Exception:
            raise

    async def _dispatch_tool(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
    ) -> Dict[str, Any]:
        """Dispatch a tool_execution task."""
        import uuid

        from app.models.workspace import Task, TaskStatus

        attempt.mark_started()
        task = Task(
            id=str(uuid.uuid4()),
            workspace_id=target_workspace_id,
            message_id=attempt.id,  # link to attempt as origin
            pack_id=phase.tool_name or "meeting_dispatch",
            task_type="tool_execution",
            status=TaskStatus.PENDING,
            params={
                "tool_name": phase.tool_name,
                "input_params": phase.input_params or {},
                "title": phase.name,
                "description": phase.description or "",
            },
            execution_context={
                "phase_id": attempt.phase_id,
                "attempt_id": attempt.id,
                "task_ir_id": attempt.task_ir_id,
                "profile_id": self.profile_id,
                "project_id": self.project_id,
            },
            project_id=self.project_id,
        )
        if self.tasks_store:
            try:
                self.tasks_store.create_task(task)
                return {"task_id": task.id, "tool_name": phase.tool_name}
            except Exception:
                raise
        return {"task_id": None, "tool_name": phase.tool_name, "dry_run": True}

    def _project_to_task(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
    ) -> Dict[str, Any]:
        """Write a projection record to legacy tasks store."""
        if self.tasks_store:
            try:
                import uuid

                from app.models.workspace import Task, TaskStatus

                task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=target_workspace_id,
                    message_id=phase.id,
                    pack_id="meeting_projection",
                    task_type="planned",
                    status=TaskStatus.PENDING,
                    params={
                        "title": phase.name,
                        "description": phase.description
                        or action_item.get("description", ""),
                    },
                    execution_context={
                        "profile_id": self.profile_id,
                        "project_id": self.project_id,
                    },
                    project_id=self.project_id,
                )
                self.tasks_store.create_task(task)
                return {"task_id": task.id, "projected": True}
            except Exception as exc:
                logger.warning("Projection write failed (non-fatal): %s", exc)
        return {"projected": False}

    # ------------------------------------------------------------------
    # Dependency gating
    # ------------------------------------------------------------------

    def _should_skip(self, phase_id: str, phase_map: Dict[str, PhaseIR]) -> bool:
        """Check if a phase should be skipped due to failed dependencies."""
        if self.skip_policy == "continue_on_dep_failure":
            return False

        phase = phase_map.get(phase_id)
        if not phase or not phase.depends_on:
            return False

        for dep_id in phase.depends_on:
            dep = phase_map.get(dep_id)
            if dep and dep.status in (PhaseStatus.FAILED, PhaseStatus.SKIPPED):
                return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_attempt(self, phase: PhaseIR, task_ir_id: str) -> PhaseAttempt:
        """Create and register a new PhaseAttempt for a phase."""
        existing = self._attempts.get(phase.id)
        attempt_number = (existing.attempt_number + 1) if existing else 1

        attempt = PhaseAttempt(
            task_ir_id=task_ir_id,
            phase_id=phase.id,
            attempt_number=attempt_number,
            target_workspace_id=phase.target_workspace_id,
        )
        self._attempts[phase.id] = attempt
        return attempt

    @staticmethod
    def _extract_playbook_code(engine: Optional[str]) -> Optional[str]:
        """Extract playbook code from engine string (e.g. 'playbook:generic')."""
        if engine and engine.startswith("playbook:"):
            return engine.split(":", 1)[1]
        return None

    def get_attempt(self, phase_id: str) -> Optional[PhaseAttempt]:
        """Get the latest attempt for a phase."""
        return self._attempts.get(phase_id)

    def get_all_attempts(self) -> Dict[str, PhaseAttempt]:
        """Get all phase attempts."""
        return dict(self._attempts)
