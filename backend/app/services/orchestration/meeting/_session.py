"""
Meeting engine session lifecycle mixin.

Handles session start/close transitions, locale resolution,
and workspace playbook discovery.
"""

import logging
from typing import Any, Dict, List, Optional

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
        self,
        minutes_md: str,
        action_items: List[Dict[str, Any]],
        dispatch_result: Optional[Dict[str, Any]] = None,
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

        # ADR-001 v2 Phase 1: Emit session_digest (L1→L2 bridge)
        try:
            from backend.app.models.personal_governance.session_digest import (
                SessionDigest,
            )
            from backend.app.services.stores.postgres.session_digest_store import (
                SessionDigestStore,
            )

            profile_id = getattr(self, "profile_id", "")
            workspace = getattr(self, "workspace", None)
            digest = SessionDigest.from_meeting_session(
                session=self.session,
                workspace=workspace,
                profile_id=profile_id,
            )
            digest_store = SessionDigestStore()
            digest_store.create(digest)
            logger.info(
                "Emitted session_digest %s for session %s",
                digest.id,
                self.session.id,
            )

            # Phase 2: Fire-and-forget extraction (PersonalKnowledge + GoalLedger)
            try:
                import asyncio
                from backend.app.services.personal_governance.digest_extraction import (
                    trigger_extraction,
                )

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(trigger_extraction(digest, self.session.id))
                else:
                    asyncio.run(trigger_extraction(digest, self.session.id))
            except Exception as ext_exc:
                logger.warning(
                    "Failed to trigger extraction for %s: %s",
                    self.session.id,
                    ext_exc,
                )

        except Exception as exc:
            logger.warning(
                "Failed to emit session_digest for %s: %s",
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
                "dispatch_result": dispatch_result,
            },
        )

    async def _async_load_installed_playbooks(self) -> str:
        """Load available playbooks for prompt injection.

        Lookup order (RAG-first, no Binding dependency):
          1. RAG search_rrf using agenda + user_message — always runs.
          2. Manifest Tier 3 fallback — scan all installed pack manifests.

        Returns:
            Formatted string listing available playbooks.
        """
        try:
            # --- Tier 1: RAG discovery (always runs) ---
            try:
                from app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                )

                rag_svc = ToolEmbeddingService()
                agenda = getattr(self.session, "agenda", []) or []
                user_msg = getattr(self, "_last_user_message", "")
                # Build query from agenda + user_message
                parts = list(agenda) + ([user_msg] if user_msg else [])
                query = "; ".join(parts) if parts else "available playbooks"

                matches, _status = await rag_svc.search_rrf(
                    query=query, top_k=10, min_score=0.25
                )
                pb_matches = [m for m in matches if m.category == "playbook"]
                if pb_matches:
                    lines = [f"- {m.tool_id}: {m.display_name}" for m in pb_matches]
                    logger.info(
                        "Playbook RAG discovery: %d playbooks for session %s",
                        len(pb_matches),
                        getattr(self.session, "id", "?"),
                    )
                    return "\n".join(lines)
            except Exception as rag_exc:
                logger.warning("Playbook RAG discovery failed: %s", rag_exc)

            # --- Tier 2: Manifest fallback — scan installed packs ---
            try:
                from app.services.stores.installed_packs_store import (
                    InstalledPacksStore,
                )
                from pathlib import Path
                import os
                import yaml as _yaml

                packs_store = InstalledPacksStore()
                pack_ids = packs_store.list_enabled_pack_ids()
                app_dir = os.getenv("APP_DIR", "/app")
                cap_dirs = [
                    Path(app_dir) / "backend" / "app" / "capabilities",
                    Path("backend/app/capabilities"),
                    Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                ]
                lines = []
                for pack_id in pack_ids:
                    for cap_base in cap_dirs:
                        manifest_path = cap_base / pack_id / "manifest.yaml"
                        if not manifest_path.exists():
                            continue
                        try:
                            with manifest_path.open("r", encoding="utf-8") as mf:
                                manifest = _yaml.safe_load(mf) or {}
                            for pb in manifest.get("playbooks", []):
                                if isinstance(pb, dict):
                                    code = pb.get("code", "")
                                    name = pb.get("name", code)
                                    if code:
                                        lines.append(f"- {code}: {name}")
                        except Exception:
                            pass
                        break
                if lines:
                    logger.info("Playbook manifest fallback: %d playbooks", len(lines))
                    return "\n".join(lines)
            except ImportError:
                pass
            except Exception as mf_exc:
                logger.warning("Playbook manifest fallback failed: %s", mf_exc)

            return "(no playbooks discovered)"
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"
