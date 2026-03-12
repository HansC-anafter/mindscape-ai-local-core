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

        Uses iterative discovery with escalation rounds instead of
        single-shot retrieval.  Each round adds candidates to a deduped
        set; search stops when confidence gate passes.

        Rounds:
          1. Scoped semantic RAG (search_rrf, category=playbook)
          2. Structural match via workspace data_sources produces/consumes
          3. Eligible subset scan (installed packs with data_sources only)
        """
        seen: set = set()
        candidates: list = []  # list of (tool_id, display_text)
        ws_id = getattr(self.session, "workspace_id", None)

        def _add(tool_id: str, text: str) -> bool:
            if tool_id in seen:
                return False
            seen.add(tool_id)
            candidates.append((tool_id, text))
            return True

        def _confidence_ok() -> bool:
            """Confidence gate: enough candidates to support LLM decision."""
            return len(candidates) >= 3

        try:
            # ── Round 1: Scoped semantic RAG ──────────────────────────
            try:
                from app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                )

                rag_svc = ToolEmbeddingService()
                agenda = getattr(self.session, "agenda", []) or []
                user_msg = getattr(self, "_last_user_message", "")
                parts = list(agenda) + ([user_msg] if user_msg else [])
                query = "; ".join(parts) if parts else "available playbooks"

                matches, _status = await rag_svc.search_rrf(
                    query=query, top_k=15, min_score=0.15
                )
                pb_matches = [m for m in matches if m.category == "playbook"]
                for m in pb_matches:
                    _add(m.tool_id, f"- {m.tool_id}: {m.display_name}")

                logger.info(
                    "Playbook discovery round=1 semantic candidates=%d "
                    "top=%s action=%s session=%s",
                    len(pb_matches),
                    pb_matches[0].tool_id if pb_matches else "none",
                    "accept" if _confidence_ok() else "escalate",
                    getattr(self.session, "id", "?"),
                )
            except Exception as rag_exc:
                logger.warning("Playbook discovery round=1 failed: %s", rag_exc)

            # ── Round 2: Structural match (produces/consumes) ─────────
            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.manifest_utils import (
                        resolve_playbook_produces,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    # Get workspace data_sources → extract available asset types
                    ws_store = PostgresWorkspacesStore()
                    ws = ws_store.get_workspace_sync(ws_id) if ws_id else None
                    ds = getattr(ws, "data_sources", None) or {}
                    available_types: set = set()
                    for _pack_id, pack_data in ds.items():
                        if isinstance(pack_data, dict):
                            for prod in pack_data.get("produces", []):
                                if isinstance(prod, dict) and prod.get("type"):
                                    available_types.add(prod["type"])

                    if available_types:
                        # Scan manifests for playbooks whose consumes match
                        app_dir = os.getenv("APP_DIR", "/app")
                        cap_dirs = [
                            Path(app_dir) / "backend" / "app" / "capabilities",
                            Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                        ]
                        from app.services.stores.installed_packs_store import (
                            InstalledPacksStore,
                        )

                        packs_store = InstalledPacksStore()
                        pack_ids = packs_store.list_enabled_pack_ids()
                        r2_count = 0
                        for pack_id in pack_ids:
                            for cap_base in cap_dirs:
                                mpath = cap_base / pack_id / "manifest.yaml"
                                if not mpath.exists():
                                    continue
                                try:
                                    with mpath.open("r", encoding="utf-8") as mf:
                                        manifest = _yaml.safe_load(mf) or {}
                                    for pb in manifest.get("playbooks", []):
                                        if not isinstance(pb, dict):
                                            continue
                                        code = pb.get("code", "")
                                        if not code or code in seen:
                                            continue
                                        # Check consumes match
                                        consumes = pb.get("consumes") or []
                                        consumes_types = {
                                            c.get("type", "")
                                            for c in consumes
                                            if isinstance(c, dict)
                                        }
                                        if consumes_types & available_types:
                                            desc = (pb.get("description") or code)[:60]
                                            if _add(code, f"- {code}: {desc}"):
                                                r2_count += 1
                                except Exception as exc:
                                    logger.warning(
                                        f"R2 Error parsing manifest for pack {pack_id}: {exc}"
                                    )
                                break

                        logger.info(
                            "Playbook discovery round=2 structural +%d "
                            "candidates=%d action=%s",
                            r2_count,
                            len(candidates),
                            "accept" if _confidence_ok() else "escalate",
                        )
                except Exception as r2_exc:
                    logger.warning("Playbook discovery round=2 failed: %s", r2_exc)

            # ── Round 3: Eligible subset scan ─────────────────────────
            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.stores.installed_packs_store import (
                        InstalledPacksStore,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    # Scope: all globally installed packs as a fallback
                    packs_store = InstalledPacksStore()
                    eligible_packs = set(packs_store.list_enabled_pack_ids())

                    app_dir = os.getenv("APP_DIR", "/app")
                    cap_dirs = [
                        Path(app_dir) / "backend" / "app" / "capabilities",
                        Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                    ]
                    r3_count = 0
                    for pack_id in eligible_packs:
                        for cap_base in cap_dirs:
                            mpath = cap_base / pack_id / "manifest.yaml"
                            if not mpath.exists():
                                continue
                            try:
                                with mpath.open("r", encoding="utf-8") as mf:
                                    manifest = _yaml.safe_load(mf) or {}
                                for pb in manifest.get("playbooks", []):
                                    if isinstance(pb, dict):
                                        code = pb.get("code", "")
                                        desc = (pb.get("description") or code)[:60]
                                        logger.info(
                                            f"R3 parsing pb={code} from pack={pack_id}"
                                        )
                                        if code and _add(code, f"- {code}: {desc}"):
                                            r3_count += 1
                                            logger.info(f"R3 added {code}")
                            except Exception as exc:
                                logger.warning(
                                    f"R3 Error parsing manifest for pack {pack_id}: {exc}"
                                )
                            break
                        else:
                            logger.info(f"R3 manifest NOT FOUND for pack {pack_id}")

                    logger.info(
                        "Playbook discovery round=3 eligible_scan +%d "
                        "candidates=%d packs=%d",
                        r3_count,
                        len(candidates),
                        len(eligible_packs),
                    )
                except Exception as r3_exc:
                    logger.warning("Playbook discovery round=3 failed: %s", r3_exc)

            if candidates:
                return "\n".join(text for _, text in candidates)
            return "(no playbooks discovered)"
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"
