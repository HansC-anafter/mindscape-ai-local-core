"""Bootstrap and store helpers for MeetingEngine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingSession
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.orchestration.meeting_agents import (
    MEETING_TOPOLOGY,
    build_meeting_roster,
)
from backend.app.services.orchestration.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


class MeetingEngineBootstrapMixin:
        def __init__(
            self,
            session: MeetingSession,
            store: Any,
            workspace: Any,
            runtime_profile: Any,
            profile_id: str,
            thread_id: Optional[str],
            project_id: Optional[str] = None,
            execution_launcher: Optional[ExecutionLauncher] = None,
            model_name: Optional[str] = None,
            executor_runtime: Optional[str] = None,
            uploaded_files: Optional[List[Dict[str, Any]]] = None,
            execution_context: Optional["MeetingExecutionContext"] = None,
        ):
            self.session = session
            # Pre-0: store contract — never None
            if store is None:
                from backend.app.services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                logger.warning(
                    "MeetingEngine received store=None, using fallback MindscapeStore"
                )
            self.store = store
            self.workspace = workspace
            self.runtime_profile = runtime_profile
            self.profile_id = profile_id
            self.thread_id = thread_id
            self.project_id = project_id
            self.session_store = MeetingSessionStore()
            self.execution_launcher = execution_launcher
            self.model_name = model_name
            self.executor_runtime = executor_runtime
            self.provider = None
            self._agent_executor = None
            self.tasks_store: Optional[TasksStore] = None
            try:
                self.tasks_store = TasksStore()
            except Exception as exc:
                logger.warning("MeetingEngine failed to initialize TasksStore: %s", exc)
            self._events: List[Any] = []
            self._turn_history: List[Dict[str, Any]] = []
            self._uploaded_files: List[Dict[str, Any]] = list(uploaded_files or [])

            # Resolve locale from workspace settings
            self._locale = self._resolve_locale(workspace)

            # A1: Resolve EffectiveLens for prompt injection + hash
            self._effective_lens = None
            self._lens_hash = None
            try:
                from backend.app.services.stores.graph_store import GraphStore
                from backend.app.services.lens.effective_lens_resolver import (
                    EffectiveLensResolver,
                )
                from backend.app.services.lens.session_override_store import (
                    InMemorySessionStore,
                )

                graph_store = GraphStore()
                session_override_store = InMemorySessionStore()
                resolver = EffectiveLensResolver(graph_store, session_override_store)
                workspace_id = getattr(workspace, "id", None) or session.workspace_id
                self._effective_lens = resolver.resolve(
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                )
                self._lens_hash = self._effective_lens.hash
            except Exception as exc:
                logger.warning("MeetingEngine failed to resolve EffectiveLens: %s", exc)

            # A1: Cache active intent IDs for prompt injection
            self._active_intent_ids = self._get_active_intent_ids()

            # Fetch project data for meeting context
            self._project_context = self._build_project_context()

            # Build workspace group asset map for cross-workspace dispatch
            self._asset_map_context = self._build_asset_map_context()

            # Build recent workflow evidence packet for meeting deliberation.
            self._workflow_evidence_context = self._build_workflow_evidence_context()

            # A4: Build dynamic roster from workspace/project context
            workspace_id = getattr(workspace, "id", None) or session.workspace_id
            self._roster = build_meeting_roster(
                workspace_id=workspace_id,
                project_id=self.project_id,
                workspace_metadata=getattr(workspace, "metadata", None),
            )

            self.orchestrator = MultiAgentOrchestrator(
                agent_roster=self._roster,
                topology=MEETING_TOPOLOGY,
                loop_budget=runtime_profile.loop_budget if runtime_profile else None,
                stop_conditions=(
                    runtime_profile.stop_conditions if runtime_profile else None
                ),
            )
            stop_conditions = getattr(runtime_profile, "stop_conditions", None)
            self.max_retries = int(getattr(stop_conditions, "max_retries", 2) or 2)
            recovery_policy = getattr(runtime_profile, "recovery_policy", None)
            self.retry_strategy = str(
                getattr(recovery_policy, "retry_strategy", "exponential_backoff")
            )

            # Assemble MeetingExecutionContext
            from backend.app.models.meeting_execution_context import (
                MeetingExecutionContext,
            )

            if execution_context is not None:
                self.ctx = execution_context
            else:
                self.ctx = MeetingExecutionContext.assemble(
                    workspace=workspace,
                    runtime_profile=runtime_profile,
                    route_decision=None,  # caller can pass via execution_context
                )

        def _get_handoff_registry_store(self):
            """Lazily instantiate HandoffRegistryStore for idempotency guard.

            Returns None if the store cannot be imported (fail-open at
            construction time — the store itself is fail-close at INSERT time).
            """
            try:
                from backend.app.services.stores.handoff_registry_store import (
                    HandoffRegistryStore,
                )
                return HandoffRegistryStore()
            except Exception as exc:
                logger.warning(
                    "MeetingEngine: HandoffRegistryStore unavailable, "
                    "idempotency guard disabled: %s",
                    exc,
                )
                return None

        def _get_pack_dispatch_adapter(self):
            """Lazily instantiate PackDispatchAdapter for spec-aware dispatch.

            Returns None if the adapter cannot be imported.
            """
            try:
                from backend.app.services.orchestration.pack_dispatch_adapter import (
                    PackDispatchAdapter,
                )
                return PackDispatchAdapter()
            except Exception as exc:
                logger.warning(
                    "MeetingEngine: PackDispatchAdapter unavailable: %s", exc
                )
                return None

        async def _emit_meeting_stage(self, stage: str, message: str) -> None:
            """Publish a meeting stage indicator via Redis for frontend display."""
            try:
                if self.session.metadata is None:
                    self.session.metadata = {}
                self.session.metadata["pipeline_stage"] = stage
                self.session.metadata["pipeline_stage_message"] = message
                self.session.metadata["pipeline_stage_updated_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self.session_store.update(self.session)
            except Exception:
                logger.debug("Meeting stage persistence failed for %s", self.session.id)
            try:
                from backend.app.services.cache.async_redis import publish_meeting_chunk

                workspace_id = (
                    getattr(self.workspace, "id", None) or self.session.workspace_id
                )
                session_id = getattr(self.session, "id", None) or ""
                await publish_meeting_chunk(
                    workspace_id,
                    {
                        "type": "meeting_stage",
                        "stage": stage,
                        "message": message,
                        "session_id": session_id,
                    },
                    getattr(self, "thread_id", None) or getattr(self.session, "thread_id", None) or session_id,
                )
            except Exception:
                pass  # non-fatal: UI just won't show the stage
