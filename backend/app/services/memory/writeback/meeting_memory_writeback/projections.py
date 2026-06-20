"""Legacy projection dispatch helpers for meeting memory writeback."""

import logging
from typing import Optional

from backend.app.models.personal_governance.session_digest import SessionDigest

logger = logging.getLogger(__name__)


def dispatch_legacy_projection(
    *,
    legacy_projection_adapter,
    digest: SessionDigest,
    session_id: str,
    source_memory_item_id: str,
    source_writeback_run_id: str,
) -> tuple[bool, Optional[str]]:
    try:
        legacy_projection_adapter.dispatch_digest_projection(
            digest,
            session_id,
            source_memory_item_id=source_memory_item_id,
            source_writeback_run_id=source_writeback_run_id,
        )
        return True, None
    except Exception as exc:
        logger.warning(
            "Legacy extraction dispatch failed for %s: %s",
            session_id,
            exc,
        )
        return False, str(exc)


def dispatch_metadata_projection(
    *,
    metadata_projection_adapter,
    digest: SessionDigest,
    session_id: str,
    source_memory_item_id: str,
    source_writeback_run_id: str,
) -> tuple[bool, Optional[str]]:
    try:
        metadata_projection_adapter.dispatch_digest_projection(
            digest,
            source_memory_item_id=source_memory_item_id,
            source_writeback_run_id=source_writeback_run_id,
        )
        return True, None
    except Exception as exc:
        logger.warning(
            "Legacy metadata projection failed for %s: %s",
            session_id,
            exc,
        )
        return False, str(exc)
