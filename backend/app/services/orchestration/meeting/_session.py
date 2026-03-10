"""
Meeting engine session lifecycle mixin.

Handles session start/close transitions, locale resolution,
and workspace playbook discovery.
"""

import logging
from typing import Any, Dict, List

from backend.app.models.meeting_session import MeetingStatus
from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingSessionMixin:
    """Mixin providing session lifecycle methods for MeetingEngine."""

    @staticmethod
    def _resolve_locale(workspace) -> str:
        """Resolve locale with fallback chain.

        Aligned with workspace_dependencies.py:100-112 get_orchestrator():
        1. workspace.default_locale
        2. system_settings "default_language"
        3. "zh-TW" hardcoded fallback
        """
        # 1. Workspace direct field
        ws_locale = getattr(workspace, "default_locale", None)
        if ws_locale:
            return ws_locale

        # 2. System settings (key = "default_language", per workspace_dependencies.py:107)
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            setting = store.get_setting("default_language")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass

        # 3. Hardcoded fallback (per blueprint_loader.py:196 + workspace_dependencies.py:111)
        return "zh-TW"

    def _start_session(self) -> None:
        """Transition session to ACTIVE and capture initial state snapshot."""
        self.session.start()
        self.session.status = MeetingStatus.ACTIVE
        self.session.state_before = self._capture_state_snapshot()

        # Feature 4: Snapshot MeetingExecutionContext into session metadata
        ctx = getattr(self, "ctx", None)
        if ctx and hasattr(ctx, "model_dump"):
            self.session.metadata["execution_context_snapshot"] = {
                "executor_runtime_id": ctx.executor_runtime_id,
                "auth_type": ctx.auth_type,
                "auth_status": ctx.auth_status,
                "fallback_model": ctx.fallback_model,
                "max_iterations": ctx.max_iterations,
                "route_kind": ctx.route_kind,
                "execution_profile": ctx.execution_profile,
            }

        self.session_store.update(self.session)
        self._emit_event(
            EventType.MEETING_START,
            payload={
                "meeting_session_id": self.session.id,
                "meeting_type": self.session.meeting_type,
                "agenda": self.session.agenda,
                "lens_id": self.session.lens_id,
            },
        )

    def _close_session(
        self, minutes_md: str, action_items: List[Dict[str, Any]]
    ) -> None:
        """Close the session with final state snapshot and minutes."""
        self.session.begin_closing()
        self.session.minutes_md = minutes_md
        self.session.action_items = action_items
        self.session.state_after = self._capture_state_snapshot()
        self.session.status = MeetingStatus.CLOSED
        self.session.close()
        self.session_store.update(self.session)

        # Feature 3: Extract structured decisions from action_items
        try:
            from backend.app.models.meeting_decision import MeetingDecision

            decisions = MeetingDecision.extract_from_session(self.session)
            if decisions:
                self.session_store.save_decisions(decisions)
                logger.info(
                    "Persisted %d decisions for session %s",
                    len(decisions),
                    self.session.id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to persist meeting decisions for %s: %s",
                self.session.id,
                exc,
            )

        self._emit_event(
            EventType.MEETING_END,
            payload={
                "meeting_session_id": self.session.id,
                "round_count": self.session.round_count,
                "action_item_count": len(action_items),
                "state_diff": self.session.state_diff,
            },
        )

    async def _async_load_installed_playbooks(self) -> str:
        """Load workspace-installed playbooks for prompt injection.

        Primary: query workspace_resource_bindings for PLAYBOOK type.
        Fallback: PlaybookService.list_playbooks() when no bindings exist.

        Returns:
            Formatted string listing available playbooks.
        """
        # TODO: binding_store is sync I/O; consider run_in_executor or async store
        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType
            from backend.app.services.playbook_service import PlaybookService

            binding_store = WorkspaceResourceBindingStore()
            bindings = binding_store.list_bindings_by_workspace(
                self.session.workspace_id, resource_type=ResourceType.PLAYBOOK
            )

            if not bindings:
                # P2: No explicit PLAYBOOK bindings — use RAG to find relevant
                # playbooks instead of dumping all into the prompt
                try:
                    from backend.app.services.tool_embedding_service import (
                        ToolEmbeddingService,
                    )

                    rag_svc = ToolEmbeddingService()
                    agenda = getattr(self.session, "agenda", []) or []
                    query = "; ".join(agenda) if agenda else ""
                    if query:
                        matches, _status = await rag_svc.search_rrf(
                            query=query, top_k=10, min_score=0.25
                        )
                        pb_matches = [m for m in matches if m.category == "playbook"]
                        if pb_matches:
                            lines = [
                                f"- {m.tool_id}: {m.display_name}" for m in pb_matches
                            ]
                            return "\n".join(lines)
                except Exception as rag_exc:
                    logger.debug("Playbook RAG fallback failed: %s", rag_exc)

                return "(no playbooks bound to this workspace)"

            svc = PlaybookService(store=self.store)
            lines = []
            for b in bindings:
                pb = await svc.get_playbook(
                    b.resource_id, workspace_id=self.session.workspace_id
                )
                # get_playbook returns Playbook — name via .metadata.name
                name = pb.metadata.name if pb else b.resource_id
                lines.append(f"- {b.resource_id}: {name}")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"
