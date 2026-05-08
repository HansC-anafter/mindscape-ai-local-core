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
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from backend.app.models.phase_attempt import (
    AttemptStatus,
    PhaseAttempt,
)
from backend.app.models.task_ir import PhaseIR, PhaseStatus, TaskIR
from backend.app.services.orchestration.playbook_alias_resolution import (
    load_playbook_spec,
    parse_playbook_codes,
    resolve_tool_name_playbook_alias,
)
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
        available_playbooks_cache: str = "",
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

        self._attempts: Dict[str, PhaseAttempt] = {}

        # Result tracking for the artifact pipeline.
        self._phase_results: Dict[str, Dict[str, Any]] = {}

        # Optional lens injector for per-phase persona context.
        self._lens_injector = lens_injector

        # Optional idempotency registry (fail-open if unavailable).
        self._handoff_registry_store = handoff_registry_store

        # Optional spec-aware dispatch adapter.
        self._pack_dispatch_adapter = pack_dispatch_adapter
        self._available_playbooks_cache = available_playbooks_cache or ""
        self._known_playbook_codes = parse_playbook_codes(self._available_playbooks_cache)
        self._playbook_spec_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._workspace_cache: Dict[str, Any] = {}

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

        # Idempotency is registered before dispatch state changes.
        if self._handoff_registry_store:
            registered = self._handoff_registry_store.register_attempt(
                idempotency_key=attempt.idempotency_key,
                task_ir_id=attempt.task_ir_id,
                phase_id=attempt.phase_id,
                attempt_number=attempt.attempt_number,
            )
            if registered is False:
                attempt.mark_skipped("duplicate_dispatch_intercepted")
                logger.warning(
                    "Dispatch for %s blocked by idempotency guard (key=%s)",
                    phase.id,
                    attempt.idempotency_key,
                )
                return {"status": "skipped", "reason": "idempotency_conflict"}
            if registered is None:
                logger.warning(
                    "Dispatch for %s proceeding without idempotency registry (key=%s)",
                    phase.id,
                    attempt.idempotency_key,
                )

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

        # Resolve target workspace
        target_ws = (
            phase.target_workspace_id
            or action_item.get("target_workspace_id")
            or getattr(self.session, "workspace_id", None)
            or ""
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

        # Rescue decomposed phases that lost playbook identity and arrived
        # as tool-like actuator names.
        rescued_playbook = self._resolve_phase_playbook_alias(phase.tool_name)
        if rescued_playbook:
            original_tool_name = phase.tool_name
            phase.preferred_engine = f"playbook:{rescued_playbook}"
            phase.tool_name = None
            action_item["tool_name_original"] = (
                action_item.get("tool_name_original")
                or action_item.get("tool_name")
                or original_tool_name
            )
            action_item["tool_name"] = None
            action_item["playbook_code"] = rescued_playbook
            action_item["tool_name_rerouted_to_playbook"] = True

        # Resolve engine/adapter — derive from phase attributes, never
        # fall back to nonexistent "generic" playbook.
        engine = phase.preferred_engine
        if not engine:
            if phase.tool_name:
                engine = f"tool:{phase.tool_name}"
            else:
                engine = "agent:auto"  # let agent pick the playbook
        playbook_code = self._extract_playbook_code(engine)

        # tool:* engine → clear playbook_code to reach tool dispatch branch
        if engine and engine.startswith("tool:"):
            playbook_code = None

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
                    ir_provenance=ir_provenance,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "launched"
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "playbook_code": playbook_code,
                        "workspace_id": target_ws,
                        "execution_id": (
                            result.get("execution_id")
                            if isinstance(result, dict)
                            else None
                        ),
                    },
                )
                return {
                    "status": "completed",
                    "workspace_id": target_ws,
                    "result": result,
                }
            elif engine.startswith("agent:"):
                result = await self._dispatch_agent(
                    phase=phase,
                    action_item=action_item,
                    target_workspace_id=target_ws,
                    attempt=attempt,
                    ir_provenance=ir_provenance,
                    engine=engine,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = result.get("status", "launched")
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "agent_id": result.get("agent_id"),
                        "workspace_id": target_ws,
                        "execution_id": result.get("execution_id"),
                    },
                )
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
                    ir_provenance=ir_provenance,
                )
                attempt.mark_completed(result)
                action_item["landing_status"] = "task_created"
                await self._publish_activity(
                    "task_dispatched",
                    {
                        "phase_id": phase.id,
                        "phase_name": phase.name,
                        "engine": engine,
                        "tool_name": phase.tool_name,
                        "workspace_id": target_ws,
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

        # Merge any explicit input_params from TaskIR phase
        extra_params = action_item.get("input_params")
        if isinstance(extra_params, dict):
            inputs.update(extra_params)
        self._apply_meeting_command_transport_context(inputs)

        # Apply spec-aware field mapping through PackDispatchAdapter.
        if self._pack_dispatch_adapter:
            try:
                inputs = self._pack_dispatch_adapter.prepare_handoff(
                    playbook_code=playbook_code,
                    raw_inputs=inputs,
                    phase=None,  # phase object not passed to this method
                    action_item=action_item,
                    session=self.session,
                    profile_id=self.profile_id,
                    project_id=self.project_id,
                )
            except Exception as exc:
                logger.warning(
                    "PackDispatchAdapter.prepare_handoff failed (non-fatal): %s", exc
                )
        self._apply_meeting_command_transport_context(inputs)

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

            execution_id = result.get("execution_id")

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
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch a tool_execution task."""
        import uuid

        from app.models.workspace import Task, TaskStatus
        from backend.app.services.executor_route_context import (
            load_executor_route_context,
        )

        attempt.mark_started()
        route_context = await load_executor_route_context(target_workspace_id)
        task = Task(
            id=str(uuid.uuid4()),
            workspace_id=target_workspace_id,
                    message_id=attempt.id,
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
                # Runner reads execution_context.inputs as tool arguments
                "inputs": phase.input_params or {},
                "tool_name": phase.tool_name,
                # v3.1 F3: capability_profile for model routing in runner
                "capability_profile": phase.capability_profile,
                "executor_route_context": route_context,
                # Feature 1: IR provenance snapshot
                **ir_provenance,
            },
            meeting_session_id=getattr(self.session, "id", None),
            project_id=self.project_id,
        )
        if self.tasks_store:
            try:
                self.tasks_store.create_task(task)
                return {"task_id": task.id, "tool_name": phase.tool_name}
            except Exception:
                raise
        return {"task_id": None, "tool_name": phase.tool_name, "dry_run": True}

    async def _dispatch_agent(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
        engine: str,
    ) -> Dict[str, Any]:
        """Dispatch a phase directly to the workspace executor runtime."""
        attempt.mark_started()

        workspace = await self._load_workspace(target_workspace_id)
        if workspace is None:
            return {
                "status": "planned",
                "reason": "workspace_not_found",
            }

        runtime_id = self._resolve_agent_runtime(
            engine=engine,
            workspace=workspace,
        )
        if not runtime_id:
            return {
                "status": "planned",
                "reason": "no_executor_runtime",
            }

        from backend.app.services.workspace_agent_executor import WorkspaceAgentExecutor

        executor = WorkspaceAgentExecutor(workspace)
        available = await executor.check_agent_available(runtime_id)
        if not available:
            raise RuntimeError(
                f"Executor {runtime_id} unavailable for workspace {target_workspace_id}"
            )

        inputs = dict(action_item.get("input_params") or phase.input_params or {})
        inputs.setdefault("workspace_id", target_workspace_id)
        if self.project_id and "project_id" not in inputs:
            inputs["project_id"] = self.project_id
        if getattr(self.session, "thread_id", None) and "thread_id" not in inputs:
            inputs["thread_id"] = getattr(self.session, "thread_id", None)
        if getattr(self.session, "id", None) and "meeting_session_id" not in inputs:
            inputs["meeting_session_id"] = getattr(self.session, "id", None)
        meeting_command_context = self._apply_meeting_command_transport_context(inputs)

        conversation_context = self._build_agent_conversation_context(
            action_item=action_item,
            inputs=inputs,
            ir_provenance=ir_provenance,
        )
        task = self._build_agent_task(
            phase=phase,
            action_item=action_item,
            inputs=inputs,
        )
        context_overrides: Dict[str, Any] = {
            "meeting_session_id": getattr(self.session, "id", None),
            "thread_id": getattr(self.session, "thread_id", None),
            "project_id": self.project_id,
            "conversation_context": conversation_context,
            "inputs": inputs,
            "ir_provenance": ir_provenance,
            "file_hint": inputs.get("deliverable_path") or "",
        }
        context_overrides.update(meeting_command_context)
        try:
            from backend.app.services.executor_route_context import (
                build_executor_route_context,
            )

            route_context = build_executor_route_context(workspace)
            if route_context:
                context_overrides["executor_route_context"] = route_context
        except Exception:
            logger.warning(
                "Failed to build executor route context for workspace %s",
                target_workspace_id,
                exc_info=True,
            )
        result = await executor.execute(
            task=task,
            agent_id=runtime_id,
            context_overrides=context_overrides,
        )
        if not result.success:
            raise RuntimeError(result.error or f"{runtime_id} execution failed")

        execution_id = result.execution_id
        if execution_id:
            attempt.adapter_meta["execution_id"] = execution_id
            if self.session:
                exec_ids = self.session.metadata.setdefault("execution_ids", [])
                if execution_id not in exec_ids:
                    exec_ids.append(execution_id)

        return {
            "status": "launched",
            "execution_id": execution_id,
            "agent_id": runtime_id,
            "trace_id": result.trace_id,
            "phase_id": attempt.phase_id,
            "attempt_id": attempt.id,
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

                from app.models.workspace import Task, TaskStatus
                from backend.app.services.executor_route_context import (
                    build_executor_route_context,
                )

                workspace = self._workspace_cache.get(target_workspace_id)
                route_context = (
                    build_executor_route_context(workspace) if workspace is not None else None
                )

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
                        "executor_route_context": route_context,
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

    def _meeting_command_transport_context(self) -> Dict[str, Any]:
        """Extract command-ledger correlation from the active MeetingEngine session."""

        metadata = getattr(self.session, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
        request_contract = metadata.get("request_contract")
        if not isinstance(request_contract, dict):
            request_contract = {}

        aol_metadata: Dict[str, Any] = {}
        for candidate in (
            request_contract.get("addressable_object_layer"),
            (
                request_contract.get("governance_constraints") or {}
            ).get("addressable_object_layer")
            if isinstance(request_contract.get("governance_constraints"), dict)
            else None,
            metadata.get("addressable_object_layer"),
        ):
            if isinstance(candidate, dict) and candidate:
                aol_metadata = dict(candidate)
                break

        command_id = (
            aol_metadata.get("command_id")
            or request_contract.get("meeting_command_id")
            or request_contract.get("command_id")
            or metadata.get("meeting_command_id")
            or metadata.get("command_id")
        )
        if isinstance(command_id, str):
            command_id = command_id.strip()
        else:
            command_id = ""

        context: Dict[str, Any] = {}
        if command_id:
            context["meeting_command_id"] = command_id
            context["command_id"] = command_id
        if aol_metadata:
            context["addressable_object_layer"] = aol_metadata
        return context

    def _apply_meeting_command_transport_context(
        self,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = self._meeting_command_transport_context()
        command_id = context.get("meeting_command_id")
        if command_id:
            inputs.setdefault("meeting_command_id", command_id)
            inputs.setdefault("command_id", command_id)
        aol_metadata = context.get("addressable_object_layer")
        if isinstance(aol_metadata, dict) and aol_metadata:
            inputs.setdefault("addressable_object_layer", aol_metadata)
        return context

    async def _load_workspace(self, workspace_id: str) -> Any:
        if not workspace_id:
            return None
        if workspace_id in self._workspace_cache:
            return self._workspace_cache[workspace_id]

        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        workspace = await PostgresWorkspacesStore().get_workspace(workspace_id)
        self._workspace_cache[workspace_id] = workspace
        return workspace

    @staticmethod
    def _resolve_agent_runtime(*, engine: str, workspace: Any) -> Optional[str]:
        if isinstance(engine, str) and engine.startswith("agent:"):
            requested_runtime = engine.split(":", 1)[1].strip()
            if requested_runtime and requested_runtime != "auto":
                return requested_runtime

        resolved_runtime = getattr(workspace, "resolved_executor_runtime", None)
        if isinstance(resolved_runtime, str) and resolved_runtime.strip():
            return resolved_runtime.strip()
        return None

    @staticmethod
    def _build_agent_task(
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> str:
        task = inputs.get("user_request")
        if isinstance(task, str) and task.strip():
            return task.strip()

        for candidate in (
            action_item.get("description"),
            phase.description,
            action_item.get("title"),
            phase.name,
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return "Complete the requested task."

    @staticmethod
    def _build_agent_conversation_context(
        *,
        action_item: Dict[str, Any],
        inputs: Dict[str, Any],
        ir_provenance: Dict[str, Any],
    ) -> str:
        sections: List[str] = []

        base_context = inputs.get("context")
        if isinstance(base_context, str) and base_context.strip():
            sections.append(base_context.strip())

        upstream_context = action_item.get("_upstream_context")
        if isinstance(upstream_context, dict) and upstream_context:
            sections.append(
                "[Upstream Context]\n"
                + json.dumps(upstream_context, ensure_ascii=False, sort_keys=True)
            )

        lens_context = action_item.get("_lens_context")
        if isinstance(lens_context, dict) and lens_context:
            sections.append(
                "[Lens Context]\n"
                + json.dumps(lens_context, ensure_ascii=False, sort_keys=True)
            )

        if ir_provenance:
            sections.append(
                "[IR Provenance]\n"
                + json.dumps(ir_provenance, ensure_ascii=False, sort_keys=True)
            )

        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _resolve_capability_profile_model(action_item: Dict[str, Any]) -> Optional[str]:
        del action_item
        return None

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
            available_playbooks_cache=self._available_playbooks_cache,
            project_id=self.project_id,
        )

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

    def _resolve_phase_playbook_alias(self, tool_name: Optional[str]) -> Optional[str]:
        """Recover playbook dispatch from tool-like decomposed phase output."""
        if not tool_name:
            return None
        return resolve_tool_name_playbook_alias(
            tool_name,
            known_playbook_codes=self._known_playbook_codes,
            get_playbook_spec=self._get_playbook_spec,
        )

    def _get_playbook_spec(self, playbook_code: str) -> Optional[Dict[str, Any]]:
        if playbook_code not in self._playbook_spec_cache:
            self._playbook_spec_cache[playbook_code] = load_playbook_spec(playbook_code)
        return self._playbook_spec_cache[playbook_code]

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
