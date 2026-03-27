"""LensPatch collector for governed-memory evidence expansion."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.memory.writeback.evidence_collectors.base import (
    EvidenceCollectionResult,
)
from backend.app.services.stores.lens_patch_store import LensPatchStore
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)

logger = logging.getLogger(__name__)


class LensPatchEvidenceCollector:
    """Attach lens-version deltas as supporting governance evidence."""

    summary_key = "lens_patch"

    def __init__(
        self,
        *,
        evidence_link_store: MemoryEvidenceLinkStore,
        lens_patch_store: Optional[LensPatchStore] = None,
    ) -> None:
        self.evidence_link_store = evidence_link_store
        self.lens_patch_store = lens_patch_store or LensPatchStore()

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        session_id = getattr(session, "id", "")
        try:
            patches = self._select_relevant_patches(session_id)
            created_count = 0
            for patch in patches:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="lens_patch",
                    evidence_id=patch.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
                    MemoryEvidenceLink.from_lens_patch(memory_item_id, patch)
                )
                created_count += 1

            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                found_count=len(patches),
                created_count=created_count,
            )
        except Exception as exc:
            logger.warning(
                "Lens patch evidence attachment failed for %s: %s",
                session_id,
                exc,
            )
            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                error=str(exc),
            )

    def _select_relevant_patches(self, session_id: str) -> list[Any]:
        patches = self.lens_patch_store.get_by_session(session_id)
        meaningful = [patch for patch in patches if getattr(patch, "delta", None)]
        if meaningful:
            return meaningful
        return patches[:1]
