"""Projection adapter from canonical meeting memory rows to legacy governance tables."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.personal_governance.digest_extraction import (
    trigger_extraction,
)


class LegacyGovernanceProjectionAdapter:
    """Materialize canonical meeting memory into legacy governance surfaces."""

    def __init__(
        self,
        extraction_trigger: Optional[
            Callable[[SessionDigest, str, Optional[Dict[str, Any]]], Awaitable[None]]
        ] = None,
    ) -> None:
        self._extraction_trigger = extraction_trigger or trigger_extraction

    def dispatch_digest_projection(
        self,
        digest: SessionDigest,
        meta_session_id: str,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
        projection_stage: str = "legacy_governance_v1",
    ) -> None:
        projection_context = {
            "source_memory_item_id": source_memory_item_id,
            "source_writeback_run_id": source_writeback_run_id,
            "projection_stage": projection_stage,
            "source_digest_id": digest.id,
        }
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                self._extraction_trigger(
                    digest,
                    meta_session_id,
                    projection_context=projection_context,
                )
            )
            return
        asyncio.run(
            self._extraction_trigger(
                digest,
                meta_session_id,
                projection_context=projection_context,
            )
        )
