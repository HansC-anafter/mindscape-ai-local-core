"""
DispatchOrchestrator — DAG walker with dependency gating.

Replaces BridgeDispatcher with a proper DAG-walking dispatcher that
tracks PhaseAttempts, respects dependency ordering, and writes
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
import inspect
import json
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from backend.app.models.phase_attempt import (
    AttemptStatus,
    PhaseAttempt,
)
from backend.app.models.task_ir import PhaseIR, PhaseStatus, TaskIR
from backend.app.services.orchestration.dispatch_orchestrator_core.planner import (
    build_ir_provenance,
    derive_research_context,
    extract_playbook_code,
    looks_like_ig_work,
    normalize_phase_inputs,
)

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
        on_wave_complete=None,
        lens_injector=None,
        handoff_registry_store=None,
        pack_dispatch_adapter=None,
    ):
        self.execution_launcher = execution_launcher
        self.tasks_store = tasks_store
        self.session = session
        self.profile_id = profile_id
        self.project_id = project_id
        self.skip_policy = skip_policy

        # Optional supervisor callback after each wave.
        # Signature: async (wave_summary, task_ir) -> Optional[List[PhaseIR]]
        self._on_wave_complete = on_wave_complete

        # PhaseAttempt tracking (phase_id -> latest attempt).
        self._attempts: Dict[str, PhaseAttempt] = {}

        # Result tracking for the artifact pipeline.
        self._phase_results: Dict[str, Dict[str, Any]] = {}

        # Optional lens injector for per-phase persona context.
        self._lens_injector = lens_injector

        # Optional idempotency registry (fail-open if unavailable).
        self._handoff_registry_store = handoff_registry_store

        # Optional spec-aware dispatch adapter.
        self._pack_dispatch_adapter = pack_dispatch_adapter

        # Best-effort execution context carried across one execute() call.
        self._current_governance: Any = None
        self._workspace_runtime_context_cache: Dict[str, Dict[str, Any]] = {}

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
        self._normalize_phase_inputs(phases, action_items)
        self._current_governance = self._extract_governance_context(task_ir)
        self._workspace_runtime_context_cache = {}

        # Activity stream: dispatch started
        await self._publish_activity(
            "dispatch_started",
            {
                "task_ir_id": task_ir.task_id,
                "total_phases": len(phases),
            },
        )
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

        items_by_intent_id, items_by_title = self._build_action_item_lookups(
            action_items
        )

        # Wave-based DAG walk
        while ready:
            # Dispatch all ready phases concurrently
            dispatch_tasks = []
            for pid in ready:
                phase = phase_map[pid]
                item = self._resolve_action_item_for_phase(
                    phase=phase,
                    action_items=action_items,
                    items_by_intent_id=items_by_intent_id,
                    items_by_title=items_by_title,
                )
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
                    # G1: Store result for downstream artifact pipeline
                    phase_result = result.get("result")
                    if isinstance(phase_result, dict):
                        self._phase_results[pid] = phase_result
                    ws = result.get("workspace_id")
                    if ws:
                        workspaces.add(ws)
                elif result.get("status") == "skipped":
                    skipped_phases.add(pid)
                    phase.status = PhaseStatus.SKIPPED
                    self._mark_action_item_skipped(
                        action_item=self._resolve_action_item_for_phase(
                            phase=phase,
                            action_items=action_items,
                            items_by_intent_id=items_by_intent_id,
                            items_by_title=items_by_title,
                        ),
                        reason=str(result.get("reason") or "skipped"),
                    )
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
                            skipped_item = self._resolve_action_item_for_phase(
                                phase=phase_map[dep_pid],
                                action_items=action_items,
                                items_by_intent_id=items_by_intent_id,
                                items_by_title=items_by_title,
                            )
                            self._append_action_item_lineage(
                                action_item=skipped_item,
                                phase=phase_map[dep_pid],
                            )
                            self._mark_action_item_skipped(
                                action_item=skipped_item,
                                reason="upstream_dependency_failed",
                            )
                            # Continue unlocking downstream of skipped
                            for sub_dep in dependents.get(dep_pid, []):
                                in_degree[sub_dep] -= 1
                                if in_degree[sub_dep] == 0:
                                    next_ready.append(sub_dep)
                        else:
                            next_ready.append(dep_pid)

            ready = next_ready

            # G3: Supervisor callback — can trigger re-plan or phase injection
            if self._on_wave_complete and ready:
                try:
                    wave_summary = {
                        "completed": sorted(completed_phases),
                        "failed": sorted(failed_phases),
                        "skipped": sorted(skipped_phases),
                        "phase_results": dict(self._phase_results),
                    }
                    new_phases = await self._on_wave_complete(wave_summary, task_ir)
                    if new_phases:
                        for np in new_phases:
                            if np.id not in phase_map:
                                task_ir.phases.append(np)
                                phase_map[np.id] = np
                                in_degree[np.id] = 0
                                for dep_id in np.depends_on or []:
                                    if dep_id in phase_map:
                                        dependents[dep_id].append(np.id)
                                        in_degree[np.id] += 1
                                if in_degree[np.id] == 0:
                                    ready.append(np.id)
                        logger.info(
                            "Supervisor injected %d new phases",
                            len(new_phases),
                        )
                except Exception as exc:
                    logger.warning("Supervisor callback failed (non-fatal): %s", exc)

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

        # Activity stream: dispatch completed
        await self._publish_activity(
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
        self._append_action_item_lineage(action_item=action_item, phase=phase)

        # Idempotency guard runs before mark_dispatched() to keep
        # attempt state clean.
        if self._handoff_registry_store:
            registered = self._handoff_registry_store.register_attempt(
                idempotency_key=attempt.idempotency_key,
                task_ir_id=attempt.task_ir_id,
                phase_id=attempt.phase_id,
                attempt_number=attempt.attempt_number,
            )
            if not registered:
                attempt.mark_skipped("duplicate_dispatch_intercepted")
                logger.warning(
                    "Dispatch for %s blocked by idempotency guard (key=%s)",
                    phase.id,
                    attempt.idempotency_key,
                )
                return {"status": "skipped", "reason": "idempotency_conflict"}

        # G1: Inject upstream phase results into downstream phase
        if phase.depends_on:
            upstream_context = {}
            for dep_id in phase.depends_on:
                dep_result = self._phase_results.get(dep_id)
                if dep_result:
                    upstream_context[dep_id] = dep_result
            if upstream_context:
                action_item["_upstream_context"] = upstream_context

        # Check if action_item is pre-blocked (policy gate)
        landing_status = action_item.get("landing_status", "")
        if landing_status in ("policy_blocked", "dispatch_error", "boundary_violation"):
            attempt.mark_skipped(f"pre_blocked:{landing_status}")
            return {"status": "skipped", "reason": landing_status}

        self._hydrate_phase_deliverable_targets_from_action_item(phase, action_item)

        # Resolve target workspace
        target_ws = (
            phase.target_workspace_id
            or action_item.get("target_workspace_id")
            or getattr(self.session, "workspace_id", None)
            or ""
        )

        await self._promote_deliverable_phase_to_external_agent(
            phase=phase,
            action_item=action_item,
            target_workspace_id=target_ws,
        )

        # G4: Per-phase lens binding
        if self._lens_injector:
            try:
                lens_ctx = self._lens_injector.prepare_lens_context(
                    profile_id=self.profile_id,
                    workspace_id=target_ws,
                    session_id=getattr(self.session, "id", None),
                )
                if lens_ctx:
                    action_item["_lens_context"] = {
                        "effective_lens_hash": lens_ctx.get("effective_lens_hash"),
                        "style_rules": lens_ctx.get("style_rules"),
                        "emphasized_values": lens_ctx.get("emphasized_values"),
                        "anti_goals": lens_ctx.get("anti_goals"),
                    }
            except Exception as exc:
                logger.warning(
                    "Lens injection failed for phase %s: %s",
                    phase.id,
                    exc,
                )

        # Resolve engine/adapter — derive from phase attributes, never
        # fall back to nonexistent "generic" playbook.
        engine, playbook_code = self._normalize_phase_engine_binding(phase)

        # Build IR provenance snapshot for downstream traceability
        ir_provenance = self._build_ir_provenance(
            phase=phase,
            action_item=action_item,
            engine=engine,
        )

        # Mark dispatched
        attempt.mark_dispatched(
            engine=engine,
            playbook_code=playbook_code,
            target_workspace_id=target_ws,
            source_intent_id=getattr(phase, "source_intent_id", None),
        )

        # Execute dispatch
        try:
            if playbook_code and self.execution_launcher:
                # Playbook dispatch path
                result = await self._launch_playbook(
                    playbook_code=playbook_code,
                    phase=phase,
                    action_item=action_item,
                    target_workspace_id=target_ws,
                    attempt=attempt,
                    ir_provenance=ir_provenance,
                )
                attempt.mark_completed(result)
                execution_id = self._resolve_execution_id_from_result(result)
                self._append_action_item_lineage(
                    action_item=action_item,
                    phase=phase,
                    execution_id=execution_id,
                )
                action_item["landing_status"] = "launched"
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "playbook_code": playbook_code,
                        "workspace_id": target_ws,
                        "execution_id": execution_id,
                    },
                )
                return {
                    "status": "completed",
                    "workspace_id": target_ws,
                    "result": result,
                }
            elif phase.tool_name:
                # Tool execution path
                if self._should_execute_tool_inline(phase):
                    result = await self._execute_tool_inline(
                        phase=phase,
                        action_item=action_item,
                        target_workspace_id=target_ws,
                        attempt=attempt,
                        ir_provenance=ir_provenance,
                    )
                else:
                    result = await self._dispatch_tool(
                        phase=phase,
                        action_item=action_item,
                        target_workspace_id=target_ws,
                        attempt=attempt,
                        ir_provenance=ir_provenance,
                    )
                attempt.mark_completed(result)
                task_id = (
                    str(result.get("task_id", "")).strip()
                    if isinstance(result, dict)
                    else ""
                )
                execution_id = self._resolve_execution_id_from_result(result)
                self._append_action_item_lineage(
                    action_item=action_item,
                    phase=phase,
                    task_id=task_id or None,
                    execution_id=execution_id,
                )
                action_item["landing_status"] = "task_created"
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "tool_name": phase.tool_name,
                        "workspace_id": target_ws,
                        "task_id": task_id or None,
                        "execution_id": execution_id,
                    },
                )
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
                    ir_provenance=ir_provenance,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "planned"
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "workspace_id": target_ws,
                    },
                )
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
            await self._publish_activity(
                "task_dispatch_failed",
                {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "error": error_msg[:200],
                },
            )
            logger.warning("Phase %s dispatch failed: %s", phase.id, exc)
            return {"status": "failed", "error": error_msg}

    # ------------------------------------------------------------------
    # Adapter methods
    # ------------------------------------------------------------------

    async def _launch_playbook(
        self,
        playbook_code: str,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
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
        # Feature 1: IR provenance for downstream traceability
        inputs["ir_provenance"] = ir_provenance

        # Carry structured phase inputs (for example ProgramSpec deliverable
        # bindings) into the playbook contract, then allow action-item level
        # overrides to win if they were explicitly set later in the pipeline.
        phase_params = getattr(phase, "input_params", None)
        if isinstance(phase_params, dict):
            inputs.update(phase_params)

        extra_params = action_item.get("input_params")
        if isinstance(extra_params, dict):
            inputs.update(extra_params)

        # Apply spec-aware field mapping through PackDispatchAdapter.
        if self._pack_dispatch_adapter:
            try:
                inputs = self._pack_dispatch_adapter.prepare_handoff(
                    playbook_code=playbook_code,
                    raw_inputs=inputs,
                    phase=phase,
                    action_item=action_item,
                    session=self.session,
                    profile_id=self.profile_id,
                    project_id=self.project_id,
                )
            except Exception as exc:
                logger.warning(
                    "PackDispatchAdapter.prepare_handoff failed (non-fatal): %s", exc
                )

        # v3.1: Resolve per-agent model from capability_profile
        _cap_profile = action_item.get("capability_profile")
        if _cap_profile:
            try:
                from backend.app.services.capability_profile_resolver import (
                    CapabilityProfileResolver,
                )

                _resolved_model, _ = CapabilityProfileResolver().resolve(
                    _cap_profile
                )
                if _resolved_model:
                    inputs["_model_override"] = _resolved_model
                    logger.info(
                        "Injected _model_override=%s from capability_profile=%s",
                        _resolved_model,
                        _cap_profile,
                    )
            except Exception as exc:
                logger.warning(
                    "capability_profile resolve failed (non-fatal): %s", exc
                )

        ctx = LocalDomainContext(
            actor_id=self.profile_id,
            workspace_id=target_workspace_id,
        )
        trace_id = (
            inputs.get("trace_id")
            if isinstance(inputs.get("trace_id"), str) and inputs.get("trace_id")
            else str(_uuid.uuid4())
        )

        try:
            result = await self.execution_launcher.launch(
                playbook_code=playbook_code,
                inputs=inputs,
                ctx=ctx,
                project_id=self.project_id,
                trace_id=trace_id,
            )

            execution_id = self._resolve_execution_id_from_result(result)

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

    @staticmethod
    def _should_execute_tool_inline(phase: PhaseIR) -> bool:
        tool_name = str(getattr(phase, "tool_name", "") or "").strip()
        return tool_name in {"external_agent_execute", "core.external_agent_execute"}

    async def _execute_tool_inline(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute bridge-bound external-agent tools in the backend process.

        These tools depend on the backend process's live agent-dispatch manager.
        If we queue them to a separate runner process, availability probes can
        false-negative because that process cannot see the in-memory WS clients.
        """
        from backend.app.models.workspace import Task, TaskStatus
        from backend.app.services.orchestration.governance_engine import (
            GovernanceEngine,
        )
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )
        from backend.app.services.tools.registry import (
            get_mindscape_tool,
            register_external_agent_tools,
        )

        attempt.mark_started()

        tool_inputs = self._build_tool_inputs(phase=phase, action_item=action_item)
        tool_name = str(phase.tool_name or "").strip()
        execution_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        task = Task(
            id=execution_id,
            workspace_id=target_workspace_id,
            message_id=attempt.id,
            execution_id=execution_id,
            pack_id=tool_name or "meeting_dispatch",
            task_type="tool_execution",
            status=TaskStatus.RUNNING,
            params={
                "tool_name": tool_name,
                "input_params": tool_inputs,
                "context": (
                    dict(tool_inputs.get("context"))
                    if isinstance(tool_inputs.get("context"), dict)
                    else {}
                ),
                "title": phase.name,
                "description": phase.description or "",
            },
            execution_context={
                "phase_id": attempt.phase_id,
                "attempt_id": attempt.id,
                "task_ir_id": attempt.task_ir_id,
                "profile_id": self.profile_id,
                "project_id": self.project_id,
                "inputs": tool_inputs,
                "tool_name": tool_name,
                "capability_profile": phase.capability_profile,
                "status": "running",
                "thread_id": getattr(self.session, "thread_id", None),
                **ir_provenance,
            },
            meeting_session_id=getattr(self.session, "id", None),
            project_id=self.project_id,
            created_at=now,
            started_at=now,
        )
        if self.tasks_store:
            self.tasks_store.create_task(task)

        tool = get_mindscape_tool(tool_name)
        if tool is None and self._should_execute_tool_inline(phase):
            register_external_agent_tools()
            tool = get_mindscape_tool(tool_name)
        if tool is None:
            error_msg = f"Tool not registered: {tool_name}"
            if self.tasks_store:
                self.tasks_store.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    result={"error": error_msg, "tool_name": tool_name},
                    error=error_msg,
                    completed_at=datetime.now(timezone.utc),
                )
            raise RuntimeError(error_msg)

        tool_result = await tool.execute(
            **self._filter_tool_execute_kwargs(tool, tool_inputs)
        )
        if not isinstance(tool_result, dict):
            tool_result = {"output": str(tool_result or "")}

        success = bool(tool_result.get("success", True))
        error_msg = str(tool_result.get("error") or "").strip()
        if success and error_msg:
            success = False

        governance_result: Dict[str, Any] | None = None
        if success:
            storage_base = None
            artifacts_dir = "artifacts"
            try:
                workspace = await PostgresWorkspacesStore().get_workspace(
                    target_workspace_id
                )
                if workspace is not None:
                    storage_base = getattr(workspace, "storage_base_path", None)
                    artifacts_dir = getattr(workspace, "artifacts_dir", None) or "artifacts"
            except Exception as exc:
                logger.warning(
                    "Inline external-agent workspace lookup failed for %s: %s",
                    target_workspace_id,
                    exc,
                )

            governance_result = GovernanceEngine().process_completion(
                workspace_id=target_workspace_id,
                execution_id=execution_id,
                result_data=tool_result,
                storage_base_path=storage_base,
                artifacts_dirname=artifacts_dir,
                thread_id=getattr(self.session, "thread_id", None),
                project_id=self.project_id,
                task_id=task.id,
                playbook_code=tool_name,
            ) or {"success": False}
            if not governance_result.get("success", False):
                landing_failure = governance_result.get("landing_failure") or {}
                failure_code = str(landing_failure.get("error_code") or "").strip()
                failure_msg = str(
                    landing_failure.get("message")
                    or landing_failure.get("error")
                    or failure_code
                    or "governance_landing_failed"
                ).strip()
                tool_result = {
                    **tool_result,
                    "governance": governance_result,
                }
                if self.tasks_store:
                    self.tasks_store.update_task_status(
                        task.id,
                        TaskStatus.FAILED,
                        result=tool_result,
                        error=failure_msg,
                        completed_at=datetime.now(timezone.utc),
                    )
                raise RuntimeError(failure_msg)

        if not success:
            error_msg = error_msg or "external agent execution failed"
            if self.tasks_store:
                self.tasks_store.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    result=tool_result,
                    error=error_msg,
                    completed_at=datetime.now(timezone.utc),
                )
            raise RuntimeError(error_msg)

        terminal_result = dict(tool_result)
        if governance_result:
            terminal_result["governance"] = governance_result
        if self.tasks_store:
            self.tasks_store.update_task_status(
                task.id,
                TaskStatus.SUCCEEDED,
                result=terminal_result,
                completed_at=datetime.now(timezone.utc),
            )

        return {
            "task_id": task.id,
            "execution_id": task.execution_id or task.id,
            "tool_name": tool_name,
            "result": terminal_result,
        }

    async def _dispatch_tool(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch a tool_execution task."""
        import uuid

        from backend.app.models.workspace import Task, TaskStatus

        attempt.mark_started()
        tool_inputs = self._build_tool_inputs(phase=phase, action_item=action_item)
        task = Task(
            id=str(uuid.uuid4()),
            workspace_id=target_workspace_id,
            message_id=attempt.id,  # link to attempt as origin
            pack_id=phase.tool_name or "meeting_dispatch",
            task_type="tool_execution",
            status=TaskStatus.PENDING,
            params={
                "tool_name": phase.tool_name,
                "input_params": tool_inputs,
                "context": (
                    dict(tool_inputs.get("context"))
                    if isinstance(tool_inputs.get("context"), dict)
                    else {}
                ),
                "title": phase.name,
                "description": phase.description or "",
            },
            execution_context={
                "phase_id": attempt.phase_id,
                "attempt_id": attempt.id,
                "task_ir_id": attempt.task_ir_id,
                "profile_id": self.profile_id,
                "project_id": self.project_id,
                # Runner reads execution_context.inputs as tool arguments
                "inputs": tool_inputs,
                "tool_name": phase.tool_name,
                # v3.1 F3: capability_profile for model routing in runner
                "capability_profile": phase.capability_profile,
                # Feature 1: IR provenance snapshot
                **ir_provenance,
            },
            meeting_session_id=getattr(self.session, "id", None),
            project_id=self.project_id,
        )
        if self.tasks_store:
            try:
                self.tasks_store.create_task(task)
                return {
                    "task_id": task.id,
                    "execution_id": task.id,
                    "tool_name": phase.tool_name,
                }
            except Exception:
                raise
        return {
            "task_id": None,
            "execution_id": None,
            "tool_name": phase.tool_name,
            "dry_run": True,
        }

    def _project_to_task(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Write a projection record to legacy tasks store."""
        if self.tasks_store:
            try:
                import uuid

                from backend.app.models.workspace import Task, TaskStatus

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
                        "ir_provenance": ir_provenance,
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
        """Check if a phase should be skipped due to failed dependencies.

        Respects PhaseIR.rollback_strategy (G3):
        - 'retry': do NOT skip — supervisor should re-queue
        - 'revert': skip and signal checkpoint rollback
        - 'skip' or default: skip propagation (original behavior)
        """
        if self.skip_policy == "continue_on_dep_failure":
            return False

        phase = phase_map.get(phase_id)
        if not phase or not phase.depends_on:
            return False

        for dep_id in phase.depends_on:
            dep = phase_map.get(dep_id)
            if dep and dep.status in (PhaseStatus.FAILED, PhaseStatus.SKIPPED):
                # G3: Respect rollback_strategy
                strategy = getattr(phase, "rollback_strategy", None) or "skip"
                if strategy == "retry":
                    # Do not skip — supervisor handles retry
                    return False
                # 'revert' and 'skip' both skip the phase;
                # the supervisor callback handles checkpoint rollback for 'revert'
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

    def _build_tool_inputs(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compose tool arguments from phase inputs plus action-item overrides."""
        tool_inputs = dict(phase.input_params or {})
        extra_params = action_item.get("input_params")
        if (
            phase.tool_name in {"external_agent_execute", "core.external_agent_execute"}
            and isinstance(extra_params, dict)
        ):
            allowed_top_level = {
                "agent",
                "task",
                "allowed_tools",
                "denied_tools",
                "max_duration",
                "context",
            }
            context = (
                dict(tool_inputs.get("context"))
                if isinstance(tool_inputs.get("context"), dict)
                else {}
            )
            context_inputs = (
                dict(context.get("inputs"))
                if isinstance(context.get("inputs"), dict)
                else {}
            )
            for key, value in extra_params.items():
                if key in allowed_top_level and key != "context":
                    tool_inputs[key] = value
                    continue
                if key == "context" and isinstance(value, dict):
                    context.update(value)
                    nested_inputs = value.get("inputs")
                    if isinstance(nested_inputs, dict):
                        context_inputs.update(nested_inputs)
                    continue
                context[key] = value
                context_inputs.setdefault(key, value)
            if context_inputs:
                context["inputs"] = context_inputs
            if context:
                tool_inputs["context"] = context
        elif isinstance(extra_params, dict):
            tool_inputs.update(extra_params)

        if phase.tool_name in {
            "review.maybe_suggest_review",
            "review.record_review_completed",
        }:
            profile_id = str(tool_inputs.get("profile_id") or "").strip()
            if not profile_id:
                profile_id = str(self.profile_id or "").strip()
            if profile_id:
                tool_inputs["profile_id"] = profile_id

        return tool_inputs

    @staticmethod
    def _filter_tool_execute_kwargs(tool: Any, tool_inputs: Dict[str, Any]) -> Dict[str, Any]:
        execute = getattr(tool, "execute", None)
        if not callable(execute):
            return dict(tool_inputs or {})
        try:
            signature = inspect.signature(execute)
        except (TypeError, ValueError):
            return dict(tool_inputs or {})

        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            return dict(tool_inputs or {})

        allowed = {
            name
            for name, parameter in signature.parameters.items()
            if name != "self"
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        return {
            key: value for key, value in dict(tool_inputs or {}).items() if key in allowed
        }

    def _normalize_phase_inputs(
        self,
        phases: List[PhaseIR],
        action_items: List[Dict[str, Any]],
    ) -> None:
        """Hydrate weakly-specified meeting phases into executable inputs."""
        normalize_phase_inputs(
            phases=phases,
            action_items=action_items,
            session=self.session,
        )

    @staticmethod
    def _build_action_item_lookups(
        action_items: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        items_by_intent_id: Dict[str, Dict[str, Any]] = {}
        items_by_title: Dict[str, Dict[str, Any]] = {}
        for item in action_items:
            if not isinstance(item, dict):
                continue
            intent_id = str(item.get("intent_id") or "").strip()
            if intent_id and intent_id not in items_by_intent_id:
                items_by_intent_id[intent_id] = item
            title = str(item.get("title") or "").strip()
            if title and title not in items_by_title:
                items_by_title[title] = item
        return items_by_intent_id, items_by_title

    @staticmethod
    def _resolve_action_item_for_phase(
        *,
        phase: PhaseIR,
        action_items: List[Dict[str, Any]],
        items_by_intent_id: Dict[str, Dict[str, Any]],
        items_by_title: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_intent_id = str(
            getattr(phase, "source_intent_id", "") or ""
        ).strip()
        if source_intent_id and source_intent_id in items_by_intent_id:
            return items_by_intent_id[source_intent_id]
        phase_id = str(getattr(phase, "id", "") or "").strip()
        if phase_id and phase_id in items_by_intent_id:
            return items_by_intent_id[phase_id]
        phase_name = str(getattr(phase, "name", "") or "").strip()
        if phase_name and phase_name in items_by_title:
            return items_by_title[phase_name]
        phase_index = DispatchOrchestrator._extract_phase_index(phase_id)
        if phase_index is not None and 0 <= phase_index < len(action_items):
            item = action_items[phase_index]
            if isinstance(item, dict):
                return item
        return {}

    @staticmethod
    def _append_action_item_lineage(
        *,
        action_item: Dict[str, Any],
        phase: PhaseIR,
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> None:
        if not isinstance(action_item, dict) or not action_item:
            return

        normalized_task_id = str(task_id or "").strip() or None
        normalized_execution_id = str(execution_id or "").strip() or None
        normalized_phase_id = str(getattr(phase, "id", "") or "").strip() or None
        normalized_source_intent_id = (
            str(getattr(phase, "source_intent_id", "") or "").strip() or None
        )

        if normalized_phase_id and not action_item.get("source_phase_id"):
            action_item["source_phase_id"] = normalized_phase_id
        if normalized_source_intent_id and not action_item.get("source_intent_id"):
            action_item["source_intent_id"] = normalized_source_intent_id
        if normalized_task_id and not str(action_item.get("task_id") or "").strip():
            action_item["task_id"] = normalized_task_id
        if normalized_execution_id and not str(
            action_item.get("execution_id") or ""
        ).strip():
            action_item["execution_id"] = normalized_execution_id

        if normalized_task_id:
            task_ids = action_item.setdefault("task_ids", [])
            if isinstance(task_ids, list) and normalized_task_id not in task_ids:
                task_ids.append(normalized_task_id)
        if normalized_execution_id:
            execution_ids = action_item.setdefault("execution_ids", [])
            if (
                isinstance(execution_ids, list)
                and normalized_execution_id not in execution_ids
            ):
                execution_ids.append(normalized_execution_id)

    @staticmethod
    def _resolve_execution_id_from_result(result: Dict[str, Any] | None) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        for candidate in (
            result.get("execution_id"),
            result.get("task_id"),
        ):
            normalized = str(candidate or "").strip()
            if normalized:
                return normalized
        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            for candidate in (
                nested_result.get("execution_id"),
                nested_result.get("task_id"),
            ):
                normalized = str(candidate or "").strip()
                if normalized:
                    return normalized
        return None

    @staticmethod
    def _extract_phase_index(phase_id: str | None) -> Optional[int]:
        normalized = str(phase_id or "").strip()
        if not normalized:
            return None
        match = re.fullmatch(r"phase_(\d+)", normalized)
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _mark_action_item_skipped(
        *,
        action_item: Dict[str, Any],
        reason: str,
    ) -> None:
        if not isinstance(action_item, dict) or not action_item:
            return

        normalized_reason = str(reason or "").strip() or "skipped"
        current_status = str(action_item.get("landing_status") or "").strip()
        if current_status in {"policy_blocked", "dispatch_error", "boundary_violation"}:
            return

        status_map = {
            "upstream_dependency_failed": "dependency_blocked",
            "duplicate_dispatch_intercepted": "duplicate_skipped",
        }
        action_item["landing_status"] = status_map.get(normalized_reason, "skipped")
        action_item["skip_reason"] = normalized_reason

    def _derive_research_context(
        self,
        phase: PhaseIR,
        phase_map: Dict[str, PhaseIR],
    ) -> tuple[Optional[str], Optional[int]]:
        """Infer a research query/max_results from upstream dependency hints."""
        return derive_research_context(
            phase=phase,
            phase_map=phase_map,
            session=self.session,
        )

    @staticmethod
    def _looks_like_ig_work(text: str) -> bool:
        """Detect caption/post-oriented phases and route them to IG mode."""
        return looks_like_ig_work(text)

    @staticmethod
    def _extract_playbook_code(engine: Optional[str]) -> Optional[str]:
        """Extract playbook code from engine string (e.g. 'playbook:generic')."""
        return extract_playbook_code(engine)

    @staticmethod
    def _extract_tool_name(engine: Optional[str]) -> Optional[str]:
        """Extract tool name from engine string (e.g. 'tool:core.external_agent_execute')."""
        if not engine or not isinstance(engine, str):
            return None
        normalized = engine.strip()
        if not normalized.startswith("tool:"):
            return None
        candidate = normalized.split(":", 1)[1].strip()
        return candidate or None

    @staticmethod
    def _is_registered_tool_name(tool_name: Optional[str]) -> bool:
        """Best-effort check for known tool IDs without assuming a warmed registry."""
        normalized = str(tool_name or "").strip()
        if not normalized:
            return False

        try:
            from backend.app.services.tools.registry import get_mindscape_tool

            if get_mindscape_tool(normalized) is not None:
                return True
        except Exception:
            pass

        try:
            from backend.app.services.capability_registry import TOOL_REGISTRY

            if normalized in TOOL_REGISTRY:
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def _is_known_playbook_code(playbook_code: Optional[str]) -> bool:
        """Best-effort check for playbook codes using the local playbook loader."""
        normalized = str(playbook_code or "").strip()
        if not normalized:
            return False

        try:
            from backend.app.services.playbook_loaders import PlaybookJsonLoader

            return PlaybookJsonLoader.load_playbook_json(normalized) is not None
        except Exception:
            return False

    def _normalize_phase_engine_binding(
        self,
        phase: PhaseIR,
    ) -> tuple[str, Optional[str]]:
        """Canonicalize mis-bound phase actuators before dispatch.

        Meeting/compiler output occasionally serializes a playbook code into
        `phase.tool_name`, which makes the runner try `tool_execution` on a
        playbook identifier like `page_outline` or `cis_mind_identity`.
        Reclassify that shape back to playbook dispatch, while leaving real
        registered tools alone.
        """
        engine = str(getattr(phase, "preferred_engine", "") or "").strip()
        tool_name = str(getattr(phase, "tool_name", "") or "").strip()

        if not tool_name:
            derived_tool_name = self._extract_tool_name(engine)
            if derived_tool_name:
                tool_name = derived_tool_name
                phase.tool_name = derived_tool_name

        playbook_code = self._extract_playbook_code(engine)
        if engine.startswith("tool:"):
            playbook_code = None

        if (
            tool_name
            and not self._is_registered_tool_name(tool_name)
            and self._is_known_playbook_code(tool_name)
        ):
            playbook_code = tool_name
            engine = f"playbook:{tool_name}"
            phase.preferred_engine = engine
            phase.tool_name = None
            logger.info(
                "Reclassified phase %s actuator %s from tool dispatch to playbook dispatch",
                getattr(phase, "id", None),
                tool_name,
            )
            return engine, playbook_code

        if not engine:
            if tool_name:
                engine = f"tool:{tool_name}"
            elif getattr(phase, "playbook_code", None):
                engine = f"playbook:{phase.playbook_code}"
            else:
                engine = "agent:auto"
            phase.preferred_engine = engine

        playbook_code = self._extract_playbook_code(engine)
        if engine.startswith("tool:"):
            playbook_code = None
        return engine, playbook_code

    def _build_ir_provenance(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        engine: str,
    ) -> Dict[str, Any]:
        """Build a provenance snapshot without assuming optional PhaseIR fields exist."""
        return build_ir_provenance(
            phase=phase,
            action_item=action_item,
            engine=engine,
            session=self.session,
        )

    async def _publish_activity(self, event_type: str, data: dict) -> None:
        """Publish event to workspace activity stream (fire-and-forget)."""
        try:
            from backend.app.services.cache.async_redis import publish_meeting_chunk

            ws_id = getattr(self.session, "workspace_id", None) or ""
            thread_id = getattr(self.session, "thread_id", None) or getattr(self.session, "id", None) or ""
            if ws_id:
                await publish_meeting_chunk(
                    ws_id,
                    {
                        "type": event_type,
                        **data,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    thread_id,
                )
        except Exception:
            pass  # non-fatal

    def get_attempt(self, phase_id: str) -> Optional[PhaseAttempt]:
        """Get the latest attempt for a phase."""
        return self._attempts.get(phase_id)

    def get_all_attempts(self) -> Dict[str, PhaseAttempt]:
        """Get all phase attempts."""
        return dict(self._attempts)

    @staticmethod
    def _extract_governance_context(task_ir: Optional[TaskIR]) -> Any:
        metadata = getattr(task_ir, "metadata", None)
        if metadata is None:
            return None
        getter = getattr(metadata, "get_governance", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return None
        governance = getattr(metadata, "governance", None)
        return governance if isinstance(governance, dict) else None

    @staticmethod
    def _extract_deliverable_targets(phase: PhaseIR) -> List[Dict[str, Any]]:
        params = getattr(phase, "input_params", None)
        if not isinstance(params, dict):
            return []

        targets: List[Dict[str, Any]] = []
        raw_targets = params.get("deliverable_targets")
        if isinstance(raw_targets, list):
            for raw_target in raw_targets:
                if not isinstance(raw_target, dict):
                    continue
                normalized = {
                    key: str(raw_target.get(key) or "").strip()
                    for key in ("deliverable_id", "deliverable_name", "deliverable_path")
                    if str(raw_target.get(key) or "").strip()
                }
                if normalized:
                    targets.append(normalized)

        single_target = {
            key: str(params.get(key) or "").strip()
            for key in ("deliverable_id", "deliverable_name", "deliverable_path")
            if str(params.get(key) or "").strip()
        }
        if single_target:
            seen = {
                (
                    target.get("deliverable_id"),
                    target.get("deliverable_name"),
                    target.get("deliverable_path"),
                )
                for target in targets
            }
            key = (
                single_target.get("deliverable_id"),
                single_target.get("deliverable_name"),
                single_target.get("deliverable_path"),
            )
            if key not in seen:
                targets.insert(0, single_target)
        return targets

    @staticmethod
    def _hydrate_phase_deliverable_targets_from_action_item(
        phase: PhaseIR,
        action_item: Dict[str, Any],
    ) -> None:
        action_params = action_item.get("input_params")
        if not isinstance(action_params, dict):
            return

        phase_params = getattr(phase, "input_params", None)
        if not isinstance(phase_params, dict):
            phase_params = {}
            phase.input_params = phase_params

        raw_action_targets = action_params.get("deliverable_targets")
        if (
            isinstance(raw_action_targets, list)
            and raw_action_targets
            and not isinstance(phase_params.get("deliverable_targets"), list)
        ):
            normalized_targets: List[Dict[str, str]] = []
            for raw_target in raw_action_targets:
                if not isinstance(raw_target, dict):
                    continue
                normalized = {
                    key: str(raw_target.get(key) or "").strip()
                    for key in ("deliverable_id", "deliverable_name", "deliverable_path")
                    if str(raw_target.get(key) or "").strip()
                }
                if normalized:
                    normalized_targets.append(normalized)
            if normalized_targets:
                phase_params["deliverable_targets"] = normalized_targets

        for key in ("deliverable_id", "deliverable_name", "deliverable_path"):
            existing = str(phase_params.get(key) or "").strip()
            if existing:
                continue
            candidate = str(action_params.get(key) or "").strip()
            if candidate:
                phase_params[key] = candidate

    def _resolve_governance_deliverables_for_phase(
        self,
        phase: PhaseIR,
    ) -> List[Dict[str, Any]]:
        governance = self._current_governance
        if governance is None:
            return []
        raw_deliverables = getattr(governance, "deliverables", None)
        if not isinstance(raw_deliverables, list):
            return []

        targets = self._extract_deliverable_targets(phase)
        target_ids = {
            str(target.get("deliverable_id") or "").strip()
            for target in targets
            if str(target.get("deliverable_id") or "").strip()
        }
        target_names = {
            str(target.get("deliverable_name") or "").strip()
            for target in targets
            if str(target.get("deliverable_name") or "").strip()
        }
        target_paths = {
            str(target.get("deliverable_path") or "").strip()
            for target in targets
            if str(target.get("deliverable_path") or "").strip()
        }

        matched: List[Dict[str, Any]] = []
        for raw in raw_deliverables:
            if hasattr(raw, "model_dump"):
                candidate = raw.model_dump(mode="json")
            elif isinstance(raw, dict):
                candidate = dict(raw)
            else:
                continue

            candidate_id = str(candidate.get("id") or "").strip()
            candidate_name = str(candidate.get("name") or "").strip()
            if (
                (candidate_id and candidate_id in target_ids)
                or (candidate_name and candidate_name in target_names)
                or (candidate_name and candidate_name in target_paths)
            ):
                matched.append(candidate)
        return matched

    def _should_reroute_deliverable_phase_to_external_agent(
        self,
        phase: PhaseIR,
    ) -> bool:
        tool_name = str(getattr(phase, "tool_name", "") or "").strip()
        preferred_engine = str(getattr(phase, "preferred_engine", "") or "").strip()
        if tool_name in {"external_agent_execute", "core.external_agent_execute"}:
            return False
        if preferred_engine in {
            "tool:external_agent_execute",
            "tool:core.external_agent_execute",
        }:
            return False
        if tool_name.startswith("filesystem_"):
            return False
        if not tool_name and preferred_engine and not preferred_engine.startswith("agent:"):
            return False

        targets = self._extract_deliverable_targets(phase)
        if not targets:
            return False

        governance_deliverables = self._resolve_governance_deliverables_for_phase(phase)
        requested_output_type = str(
            getattr(self._current_governance, "requested_output_type", "") or ""
        ).strip()
        if requested_output_type == "text/markdown":
            return True
        for target in targets:
            deliverable_path = str(target.get("deliverable_path") or "").strip().lower()
            if deliverable_path.endswith(".md"):
                return True
        for deliverable in governance_deliverables:
            if str(deliverable.get("mime_type") or "").strip().lower() == "text/markdown":
                return True
        return False

    async def _resolve_workspace_runtime_context(
        self,
        workspace_id: str,
    ) -> Dict[str, Any]:
        normalized_workspace_id = str(workspace_id or "").strip()
        if not normalized_workspace_id:
            return {}
        cached = self._workspace_runtime_context_cache.get(normalized_workspace_id)
        if cached is not None:
            return dict(cached)

        resolved: Dict[str, Any] = {}
        try:
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            workspace = await PostgresWorkspacesStore().get_workspace(normalized_workspace_id)
        except Exception:
            workspace = None

        if workspace is not None:
            storage_base = str(getattr(workspace, "storage_base_path", "") or "").strip()
            executor_runtime = str(getattr(workspace, "executor_runtime", "") or "").strip()
            if storage_base:
                resolved["workspace_storage_base"] = storage_base
            if executor_runtime:
                resolved["agent_id"] = executor_runtime

        session_metadata = getattr(self.session, "metadata", None) or {}
        execution_snapshot = session_metadata.get("execution_context_snapshot")
        if isinstance(execution_snapshot, dict):
            runtime_id = str(execution_snapshot.get("executor_runtime_id") or "").strip()
            if runtime_id and not resolved.get("agent_id"):
                resolved["agent_id"] = runtime_id
        target_client_id = str(session_metadata.get("executor_target_client_id") or "").strip()
        if target_client_id:
            resolved["target_client_id"] = target_client_id

        if not resolved.get("agent_id"):
            resolved["agent_id"] = "codex_cli"

        if not resolved.get("workspace_storage_base"):
            # Match WorkspaceAgentExecutor's fallback workspace root so deliverable
            # phases can still bind to a workspace-scoped external-agent sandbox
            # even when the ephemeral workspace record is not yet persisted.
            resolved["workspace_storage_base"] = (
                f"/tmp/mindscape/workspaces/{normalized_workspace_id}"
            )

        self._workspace_runtime_context_cache[normalized_workspace_id] = dict(resolved)
        return resolved

    @staticmethod
    def _render_prompt_section(title: str, body: str) -> str:
        normalized_body = str(body or "").strip()
        if not normalized_body:
            return ""
        return f"{title}:\n{normalized_body}"

    def _build_external_agent_deliverable_task(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
    ) -> str:
        targets = self._extract_deliverable_targets(phase)
        governance_deliverables = self._resolve_governance_deliverables_for_phase(phase)
        governance = self._current_governance

        prompt_lines = [
            "Create the requested workspace deliverable in markdown.",
            "Write the file inside the current workspace sandbox and also return a concise completion summary.",
            "Do not leave placeholders such as TODO, TBD, 待補, or placeholder.",
        ]

        if len(targets) == 1:
            target = targets[0]
            deliverable_path = str(target.get("deliverable_path") or "").strip()
            deliverable_name = str(target.get("deliverable_name") or "").strip()
            if deliverable_path:
                prompt_lines.append(f"Target file: {deliverable_path}")
            if deliverable_name:
                prompt_lines.append(f"Deliverable: {deliverable_name}")
        elif targets:
            prompt_lines.append("Create all of these deliverables:")
            for target in targets:
                prompt_lines.append(
                    "- {path} :: {name}".format(
                        path=str(target.get("deliverable_path") or "(unnamed)").strip(),
                        name=str(target.get("deliverable_name") or "").strip() or "deliverable",
                    )
                )

        phase_summary = "\n".join(
            line
            for line in (
                f"Phase: {str(getattr(phase, 'name', '') or '').strip()}",
                f"Description: {str(getattr(phase, 'description', '') or '').strip()}",
                f"Action item: {str(action_item.get('description') or action_item.get('title') or '').strip()}",
            )
            if line.split(":", 1)[1].strip()
        )
        if phase_summary:
            prompt_lines.append("")
            prompt_lines.append(self._render_prompt_section("Workstream Context", phase_summary))

        if governance is not None:
            goals = getattr(governance, "goals", None)
            if isinstance(goals, list) and goals:
                prompt_lines.append("")
                prompt_lines.append(
                    self._render_prompt_section(
                        "Goals",
                        "\n".join(f"- {str(goal).strip()}" for goal in goals if str(goal).strip()),
                    )
                )
            non_goals = getattr(governance, "non_goals", None)
            if isinstance(non_goals, list) and non_goals:
                prompt_lines.append("")
                prompt_lines.append(
                    self._render_prompt_section(
                        "Non-Goals",
                        "\n".join(
                            f"- {str(non_goal).strip()}"
                            for non_goal in non_goals
                            if str(non_goal).strip()
                        ),
                    )
                )
            human_instructions = str(
                getattr(governance, "human_instructions", "") or ""
            ).strip()
            if human_instructions:
                prompt_lines.append("")
                prompt_lines.append(
                    self._render_prompt_section("Human Instructions", human_instructions)
                )

        if governance_deliverables:
            deliverable_lines: List[str] = []
            for deliverable in governance_deliverables:
                line_parts = []
                name = str(deliverable.get("name") or "").strip()
                description = str(deliverable.get("description") or "").strip()
                mime_type = str(deliverable.get("mime_type") or "").strip()
                if name:
                    line_parts.append(name)
                if description:
                    line_parts.append(description)
                if mime_type:
                    line_parts.append(f"mime={mime_type}")
                if line_parts:
                    deliverable_lines.append("- " + " | ".join(line_parts))
            if deliverable_lines:
                prompt_lines.append("")
                prompt_lines.append(
                    self._render_prompt_section(
                        "Deliverable Requirements",
                        "\n".join(deliverable_lines),
                    )
                )

        upstream_context = action_item.get("_upstream_context")
        if isinstance(upstream_context, dict) and upstream_context:
            try:
                upstream_text = json.dumps(
                    upstream_context,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            except Exception:
                upstream_text = str(upstream_context)
            prompt_lines.append("")
            prompt_lines.append(
                self._render_prompt_section("Upstream Phase Outputs", upstream_text[:4000])
            )

        return "\n".join(line for line in prompt_lines if line).strip()

    async def _promote_deliverable_phase_to_external_agent(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
    ) -> None:
        if not self._should_reroute_deliverable_phase_to_external_agent(phase):
            return

        runtime_context = await self._resolve_workspace_runtime_context(target_workspace_id)
        storage_base = str(runtime_context.get("workspace_storage_base") or "").strip()
        agent_id = str(runtime_context.get("agent_id") or "").strip()
        if not storage_base or not agent_id:
            logger.warning(
                "Deliverable phase %s kept original tool %s because workspace runtime context is incomplete",
                getattr(phase, "id", None),
                getattr(phase, "tool_name", None),
            )
            return

        deliverable_targets = self._extract_deliverable_targets(phase)
        original_tool_name = str(getattr(phase, "tool_name", "") or "").strip()
        transport_inputs: Dict[str, Any] = {}
        if deliverable_targets:
            transport_inputs["deliverable_targets"] = [dict(target) for target in deliverable_targets]
            primary = deliverable_targets[0]
            for key in ("deliverable_id", "deliverable_name", "deliverable_path"):
                value = str(primary.get(key) or "").strip()
                if value:
                    transport_inputs[key] = value

        agent_context: Dict[str, Any] = {
            "workspace_id": target_workspace_id,
            "workspace_storage_base": storage_base,
            "project_id": self.project_id,
            "thread_id": getattr(self.session, "thread_id", None),
            "auth_workspace_id": target_workspace_id,
            "source_workspace_id": target_workspace_id,
            "intent_id": str(getattr(phase, "source_intent_id", "") or phase.id).strip(),
            "inputs": dict(transport_inputs),
        }
        for key, value in transport_inputs.items():
            agent_context[key] = value

        target_client_id = str(runtime_context.get("target_client_id") or "").strip()
        if target_client_id:
            agent_context["target_client_id"] = target_client_id
        if original_tool_name:
            agent_context["source_tool_name"] = original_tool_name

        phase.tool_name = "core.external_agent_execute"
        phase.preferred_engine = "tool:core.external_agent_execute"
        phase.input_params = {
            "agent": agent_id,
            "task": self._build_external_agent_deliverable_task(
                phase=phase,
                action_item=action_item,
            ),
            "max_duration": 900,
            "context": agent_context,
        }
        logger.info(
            "Promoted deliverable phase %s from tool %s to external agent %s",
            getattr(phase, "id", None),
            original_tool_name or "(none)",
            agent_id,
        )
