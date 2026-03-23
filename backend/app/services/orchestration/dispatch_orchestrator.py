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
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
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

        # Resolve engine/adapter — derive from phase attributes, never
        # fall back to nonexistent "generic" playbook.
        engine = phase.preferred_engine
        if not engine:
            if phase.tool_name:
                engine = f"tool:{phase.tool_name}"
            elif getattr(phase, "playbook_code", None):
                engine = f"playbook:{phase.playbook_code}"
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
        ir_provenance: Dict[str, Any],
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
                # Runner reads execution_context.inputs as tool arguments
                "inputs": phase.input_params or {},
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
                return {"task_id": task.id, "tool_name": phase.tool_name}
            except Exception:
                raise
        return {"task_id": None, "tool_name": phase.tool_name, "dry_run": True}

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

    def _normalize_phase_inputs(
        self,
        phases: List[PhaseIR],
        action_items: List[Dict[str, Any]],
    ) -> None:
        """Hydrate weakly-specified meeting phases into executable inputs.

        The meeting decomposer often emits placeholders like ``source_uri`` or
        omits research queries entirely. Normalize the known
        ``frontier_research -> article_draft`` chain so dispatch receives a
        runnable contract instead of empty input dicts.
        """
        phase_map: Dict[str, PhaseIR] = {p.id: p for p in phases}
        items_by_title: Dict[str, Dict[str, Any]] = {
            item.get("title", ""): item for item in action_items if item.get("title")
        }
        for phase in phases:
            params = dict(phase.input_params or {})
            changed = False

            if phase.tool_name == "frontier_research.process_papers_pipeline":
                query, max_results = self._derive_research_context(phase, phase_map)
                if not params.get("query") and query:
                    params["query"] = query
                    changed = True
                if not params.get("max_results") and max_results:
                    params["max_results"] = max_results
                    changed = True
                if not params.get("sources"):
                    params["sources"] = ["pubmed", "semantic_scholar"]
                    changed = True

            playbook_code = self._extract_playbook_code(phase.preferred_engine)
            if playbook_code == "article_draft":
                query, max_results = self._derive_research_context(phase, phase_map)
                if not params.get("topic") and query:
                    params["topic"] = query
                    changed = True
                if not params.get("workspace_id"):
                    workspace_id = phase.target_workspace_id or getattr(
                        self.session, "workspace_id", None
                    )
                    if workspace_id:
                        params["workspace_id"] = workspace_id
                        changed = True
                if not params.get("max_results") and max_results:
                    params["max_results"] = max_results
                    changed = True
                if not params.get("sources"):
                    params["sources"] = ["pubmed", "semantic_scholar"]
                    changed = True
                if not params.get("language"):
                    params["language"] = "zh-TW"
                    changed = True

                phase_text = " ".join(
                    filter(None, [phase.name, phase.description or ""])
                )
                if not params.get("target_format") and self._looks_like_ig_work(
                    phase_text
                ):
                    params["target_format"] = "ig_caption"
                    changed = True

            if changed:
                phase.input_params = params
                item = items_by_title.get(phase.name)
                if item is not None:
                    item["input_params"] = dict(params)

    def _derive_research_context(
        self,
        phase: PhaseIR,
        phase_map: Dict[str, PhaseIR],
    ) -> tuple[Optional[str], Optional[int]]:
        """Infer a research query/max_results from upstream dependency hints."""
        queries: List[str] = []
        max_results: List[int] = []
        visited: Set[str] = set()

        def visit(phase_id: str) -> None:
            if phase_id in visited:
                return
            visited.add(phase_id)
            dep = phase_map.get(phase_id)
            if dep is None:
                return

            params = dep.input_params or {}
            query = params.get("query") or params.get("topic")
            if isinstance(query, str) and query.strip():
                queries.append(query.strip())

            limit = params.get("max_results")
            if isinstance(limit, int) and limit > 0:
                max_results.append(limit)

            for upstream_id in dep.depends_on or []:
                visit(upstream_id)

        for dep_id in phase.depends_on or []:
            visit(dep_id)

        if not queries:
            params = phase.input_params or {}
            query = params.get("query") or params.get("topic")
            if isinstance(query, str) and query.strip():
                queries.append(query.strip())

        if not queries:
            agenda = getattr(self.session, "agenda", None) or []
            if isinstance(agenda, list):
                for item in agenda:
                    if isinstance(item, str) and item.strip():
                        queries.append(item.strip())
                        break

        query = queries[0] if queries else None
        derived_limit = sum(max_results) if max_results else None
        return query, derived_limit

    @staticmethod
    def _looks_like_ig_work(text: str) -> bool:
        """Detect caption/post-oriented phases and route them to IG mode."""
        return bool(
            re.search(
                r"\b(ig|instagram|caption|post|posts)\b|貼文",
                (text or "").lower(),
            )
        )

    @staticmethod
    def _extract_playbook_code(engine: Optional[str]) -> Optional[str]:
        """Extract playbook code from engine string (e.g. 'playbook:generic')."""
        if engine and engine.startswith("playbook:"):
            return engine.split(":", 1)[1]
        return None

    def _build_ir_provenance(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        engine: str,
    ) -> Dict[str, Any]:
        """Build a provenance snapshot without assuming optional PhaseIR fields exist."""
        dependencies = phase.depends_on or action_item.get("depends_on")
        if dependencies is None:
            dependencies = action_item.get("blocked_by") or []

        return {
            "preferred_engine": engine,
            "tool_name": phase.tool_name,
            "rationale": getattr(phase, "rationale", None)
            or action_item.get("rationale"),
            "dependencies": list(dependencies or []),
            "meeting_session_id": getattr(self.session, "id", None),
            "phase_id": phase.id,
            "priority": getattr(phase, "priority", None) or action_item.get("priority"),
        }

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
