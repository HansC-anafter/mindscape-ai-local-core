"""Pre-prepare local modification review for capability installs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from ..paths import (
    OVERWRITE_CONFIRMATION_PHRASE,
    OVERWRITE_REVIEW_CONFIRMATION_PHRASE,
    _build_dirty_overwrite_detail,
)


async def validate_existing_install_dirty_state(
    *,
    existing_cap_dir: Path,
    candidate_cap_dir: Path,
    capability_code: str,
    incoming_version: str,
    allow_overwrite: bool,
    overwrite_review_confirmation: str,
    run_in_threadpool_func: Callable[..., Awaitable[Any]],
) -> None:
    """Fail before prepare when local modifications lack exact review approval."""

    if not existing_cap_dir.exists():
        return
    from app.services.install_integrity import (
        build_dirty_review_payload,
        check_dirty_state,
    )

    dirty = await run_in_threadpool_func(check_dirty_state, existing_cap_dir)
    if not dirty.is_dirty:
        return
    review_payload = await run_in_threadpool_func(
        build_dirty_review_payload,
        existing_cap_dir,
        candidate_cap_dir,
        dirty,
    )
    if not allow_overwrite:
        raise HTTPException(
            status_code=409,
            detail=_build_dirty_overwrite_detail(
                dirty=dirty,
                incoming_version=incoming_version,
                review_payload=review_payload,
                error="local_modifications_detected",
                message=(
                    f"{capability_code}: {len(dirty.modified)} modified, "
                    f"{len(dirty.added)} added, {len(dirty.deleted)} deleted "
                    f"since v{dirty.installed_version} install"
                ),
                hint=(
                    "Review every file diff, then resubmit with allow_overwrite=true, "
                    f"overwrite_confirmation={OVERWRITE_CONFIRMATION_PHRASE}, and "
                    "the exact overwrite review confirmation."
                ),
            ),
        )
    if (
        str(overwrite_review_confirmation or "").strip()
        != OVERWRITE_REVIEW_CONFIRMATION_PHRASE
    ):
        raise HTTPException(
            status_code=409,
            detail=_build_dirty_overwrite_detail(
                dirty=dirty,
                incoming_version=incoming_version,
                review_payload=review_payload,
                error="overwrite_review_confirmation_required",
                message="Force overwrite is blocked until local diffs are reviewed.",
                hint=(
                    "Inspect every diff and resubmit with the exact overwrite review "
                    "confirmation only when the candidate preserves required fixes."
                ),
            ),
        )
