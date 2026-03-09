"""
Meeting engine L2/L3 bridge pipeline mixin.

Handles post-session extraction: MeetingExtract, GoalLinking,
LensPatch, and StateVector computation.
"""

import logging
from typing import Any

from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingL2BridgeMixin:
    """Mixin providing L2/L3 bridge pipeline for MeetingEngine."""

    def _run_l2_bridge_pipeline(self) -> None:
        """Run L2 Bridge extraction pipeline after session close.

        Pipeline: events → MeetingExtract → GoalLinking → LensPatch
        All failures are non-fatal (logged, never breaks the meeting).
        """
        try:
            from backend.app.services.orchestration.meeting.extract_service import (
                MeetingExtractService,
            )
            from backend.app.services.orchestration.meeting.lens_patch_service import (
                LensPatchService,
            )
            from backend.app.services.orchestration.meeting.goal_linking_service import (
                GoalLinkingService,
            )
            from backend.app.services.stores.meeting_extract_store import (
                MeetingExtractStore,
            )
            from backend.app.services.stores.lens_patch_store import LensPatchStore
            from backend.app.services.stores.goal_set_store import GoalSetStore

            # Step 1: Extract structured items from meeting events
            extract_svc = MeetingExtractService()
            extract = extract_svc.extract_from_events(
                meeting_session_id=self.session.id,
                events=self._events,
            )

            # Step 2: Link extract items to active GoalSet (if any)
            goal_store = GoalSetStore()
            active_goals = goal_store.list_by_project(
                workspace_id=self.session.workspace_id,
                project_id=self.project_id or "",
                limit=1,
            )
            if active_goals:
                linking_svc = GoalLinkingService()
                extract = linking_svc.link_extract_to_goals(extract, active_goals[0])
                extract.goal_set_id = active_goals[0].id

            # Step 3: Persist the extract
            extract_store = MeetingExtractStore()
            extract_store.create(extract)
            logger.info(
                "L2 Bridge: persisted MeetingExtract %s (%d items) for session %s",
                extract.id,
                len(extract.items),
                self.session.id,
            )

            # Step 4: Generate lens patch (compare before/after)
            lens_after = None
            try:
                from backend.app.services.stores.graph_store import GraphStore
                from backend.app.services.lens.effective_lens_resolver import (
                    EffectiveLensResolver,
                )
                from backend.app.services.lens.session_override_store import (
                    InMemorySessionStore,
                )

                resolver = EffectiveLensResolver(GraphStore(), InMemorySessionStore())
                lens_after = resolver.resolve(
                    profile_id=self.profile_id,
                    workspace_id=self.session.workspace_id,
                )
            except Exception as exc:
                logger.debug("L2 Bridge: could not resolve post-session lens: %s", exc)

            patch_svc = LensPatchService()
            patch = patch_svc.generate_patch_from_session(
                session=self.session,
                lens_before=self._effective_lens,
                lens_after=lens_after,
            )
            if patch:
                patch_store = LensPatchStore()
                patch_store.create(patch)
                logger.info(
                    "L2 Bridge: persisted LensPatch %s for session %s",
                    patch.id,
                    self.session.id,
                )

            # Step 5: L3 StateVector computation (non-fatal)
            self._compute_state_vector(extract, active_goals, patch)

        except Exception as exc:
            logger.warning(
                "L2 Bridge pipeline failed (non-fatal) for session %s: %s",
                self.session.id,
                exc,
            )

    def _compute_state_vector(
        self,
        extract: Any,
        active_goals: list,
        patch: Any,
    ) -> None:
        """L3: Compute and persist StateVector from meeting output."""
        try:
            from backend.app.services.orchestration.meeting.state_vector_service import (
                StateVectorService,
            )
            from backend.app.services.stores.state_vector_store import (
                StateVectorStore,
            )
            from backend.app.models.meeting_mode import MeetingMode

            sv_svc = StateVectorService()
            goal_set = active_goals[0] if active_goals else None

            # Risk fallback: prefer EGB drift score, fall back to session metadata
            risk_fallback = float(self.session.metadata.get("risk_score", 0.0))
            intent_ids = self._get_active_intent_ids()
            if intent_ids:
                try:
                    from backend.app.database import get_db_postgres
                    from sqlalchemy import text

                    db_gen = get_db_postgres()
                    db = next(db_gen)
                    try:
                        row = db.execute(
                            text(
                                "SELECT overall_drift_score "
                                "FROM egb_drift_report "
                                "WHERE intent_id = :iid "
                                "ORDER BY created_at DESC LIMIT 1"
                            ),
                            {"iid": intent_ids[0]},
                        ).fetchone()
                        if row and row[0] and float(row[0]) > 0:
                            risk_fallback = max(risk_fallback, float(row[0]))
                    finally:
                        next(db_gen, None)
                except Exception:
                    pass  # EGB 不可用時回退到 session metadata

            # Session count for evidence grace period
            session_count = 0
            if self.session_store and self.project_id:
                try:
                    previous = self.session_store.list_by_workspace(
                        workspace_id=self.session.workspace_id,
                        project_id=self.project_id,
                        limit=100,
                    )
                    session_count = len(previous)
                except Exception:
                    pass

            sv = sv_svc.compute(
                meeting_session_id=self.session.id,
                workspace_id=self.session.workspace_id,
                extract=extract,
                goal_set=goal_set,
                patches=[patch] if patch else [],
                current_lens_hash=getattr(self, "_lens_hash", None) or "",
                previous_lens_hash="",
                current_mode=MeetingMode(
                    self.session.metadata.get("meeting_mode", "explore")
                ),
                session_count=session_count,
                risk_fallback=risk_fallback,
                project_id=self.project_id,
            )

            # Persist state vector
            sv_store = StateVectorStore()
            sv_store.create(sv)

            # Emit STATE_VECTOR_COMPUTED event
            self._emit_event(
                EventType.STATE_VECTOR_COMPUTED,
                payload={
                    "meeting_session_id": self.session.id,
                    "state_vector_id": sv.id,
                    "axes": {
                        "progress": sv.progress,
                        "evidence": sv.evidence,
                        "risk": sv.risk,
                        "drift": sv.drift,
                    },
                    "lyapunov_v": sv.lyapunov_v,
                    "mode": sv.mode,
                },
            )

            # Emit MODE_TRANSITION if mode changed
            prev_mode = self.session.metadata.get("meeting_mode", "explore")
            if sv.mode != prev_mode:
                self._emit_event(
                    EventType.MODE_TRANSITION,
                    payload={
                        "meeting_session_id": self.session.id,
                        "from_mode": prev_mode,
                        "to_mode": sv.mode,
                        "reason": f"StateVector triggered: V={sv.lyapunov_v:.3f}",
                    },
                )

            logger.info(
                "L3: StateVector %s computed for session %s (V=%.3f, mode=%s)",
                sv.id,
                self.session.id,
                sv.lyapunov_v,
                sv.mode,
            )
        except Exception as exc:
            logger.warning(
                "L3 StateVector computation failed (non-fatal) for session %s: %s",
                self.session.id,
                exc,
            )
