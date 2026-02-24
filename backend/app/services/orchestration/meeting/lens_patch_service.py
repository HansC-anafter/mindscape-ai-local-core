"""
Lens patch service — session close to LensPatch generation.

Compares EffectiveLens state before and after a meeting session to
produce a LensPatch delta. Supports the L2 Bridge version chain for
L3 Drift(P_t, P_{t-1}) computation.

Matches LensPatch model contract:
  - delta: Dict[str, Any] with {dimension_key: {before, after}}
  - lens_version_before / lens_version_after
  - No phantom fields (project_id, workspace_id, version, etc.)

Pipeline: session.close() -> compare lens snapshots -> LensPatch(delta)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.app.models.lens_patch import LensPatch, PatchStatus

logger = logging.getLogger(__name__)


class LensPatchService:
    """Generate lens patches from meeting session lens state changes.

    Usage:
        service = LensPatchService()
        patch = service.generate_patch_from_session(
            session=session,
            lens_before=effective_lens_before,
            lens_after=effective_lens_after,
        )
        if patch:
            patch_store.create(patch)
    """

    def generate_patch_from_session(
        self,
        session: Any,
        lens_before: Optional[Any] = None,
        lens_after: Optional[Any] = None,
    ) -> Optional[LensPatch]:
        """Compare lens states and generate a delta patch.

        Args:
            session: MeetingSession that just closed.
            lens_before: EffectiveLens at session start (or None).
            lens_after: EffectiveLens at session end (or None).

        Returns:
            LensPatch if there are meaningful differences, None if identical.
        """
        if not lens_before and not lens_after:
            return None

        hash_before = getattr(lens_before, "hash", None) if lens_before else None
        hash_after = getattr(lens_after, "hash", None) if lens_after else None

        # No change
        if hash_before == hash_after and hash_before is not None:
            logger.debug(
                "Lens unchanged for session %s (hash=%s)", session.id, hash_before
            )
            return None

        # Compute delta
        delta = self._compute_delta(lens_before, lens_after)
        if not delta:
            return None

        lens_id = getattr(session, "lens_id", None) or "unknown"

        # Use LensPatch.new() factory for correct field initialization
        patch = LensPatch.new(
            lens_id=lens_id,
            meeting_session_id=session.id,
            delta=delta,
            evidence_refs=[],
            confidence=0.5,
            lens_version_before=0,
            rollback_to=None,
        )

        logger.info(
            "Generated LensPatch %s for session %s: %d dimension changes (hash %s -> %s)",
            patch.id,
            session.id,
            len(delta),
            hash_before,
            hash_after,
        )

        return patch

    def _compute_delta(
        self,
        lens_before: Optional[Any],
        lens_after: Optional[Any],
    ) -> Dict[str, Any]:
        """Compute structured delta between two EffectiveLens states.

        Returns dict matching LensPatch.delta contract:
        {dimension_key: {before: old_value, after: new_value}}
        """
        delta: Dict[str, Any] = {}

        before_nodes = {}
        after_nodes = {}

        if lens_before and hasattr(lens_before, "nodes"):
            before_nodes = {n.node_id: n for n in lens_before.nodes}
        if lens_after and hasattr(lens_after, "nodes"):
            after_nodes = {n.node_id: n for n in lens_after.nodes}

        all_ids = set(before_nodes.keys()) | set(after_nodes.keys())

        for node_id in all_ids:
            b = before_nodes.get(node_id)
            a = after_nodes.get(node_id)

            if b and not a:
                delta[node_id] = {"before": "present", "after": "removed"}
                continue
            if a and not b:
                delta[node_id] = {"before": "absent", "after": "added"}
                continue

            # Both exist — check for state changes
            b_state = b.state.value if hasattr(b.state, "value") else str(b.state)
            a_state = a.state.value if hasattr(a.state, "value") else str(a.state)
            if b_state != a_state:
                delta[node_id] = {"before": b_state, "after": a_state}

        return delta
