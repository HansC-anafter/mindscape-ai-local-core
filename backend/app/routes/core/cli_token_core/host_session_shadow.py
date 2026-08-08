from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.routes.core.cli_token_core.host_session_metadata import (
    _can_shadow_host_session_candidate,
    _default_pool_group_for_surface,
)
from backend.app.routes.core.cli_token_core.schemas import RegisterHostSessionRuntimeRequest
from backend.app.services.runtime_route_registration import (
    sync_runtime_registration_metadata,
)


def _get_host_session_shadow_db():
    try:
        from backend.app.database.session import get_db_postgres as get_db
    except ImportError:
        try:
            from backend.app.database import get_db_postgres as get_db
        except ImportError:
            from mindscape.di.providers import get_db_session as get_db
    return next(get_db())


def _host_session_shadow_candidate_key(
    candidate: Any,
    *,
    owner_user_id: str,
    surface: str,
    pool_group: str | None,
) -> tuple[str, str] | None:
    if str(getattr(candidate, "user_id", "") or "") != owner_user_id:
        return None
    if str(getattr(candidate, "auth_type", "") or "") != "host_session":
        return None
    if getattr(candidate, "pool_group", None) != pool_group:
        return None

    candidate_meta = dict(getattr(candidate, "extra_metadata", None) or {})
    candidate_surface = str(candidate_meta.get("surface") or "").strip().lower()
    candidate_home = str(candidate_meta.get("HOME") or "").strip()
    candidate_codex_home = str(candidate_meta.get("CODEX_HOME") or "").strip()
    candidate_workspace_id = str(
        candidate_meta.get("last_workspace_id") or ""
    ).strip()
    if candidate_surface != str(surface or "").strip().lower():
        return None
    if not candidate_home or candidate_codex_home or not candidate_workspace_id:
        return None
    if not _can_shadow_host_session_candidate(
        candidate_meta,
        request_workspace_id=candidate_workspace_id,
    ):
        return None
    return candidate_home, candidate_workspace_id


def _apply_host_session_shadow(
    *,
    candidates: list[Any],
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
    runtime_id: str,
    pool_group: str | None,
) -> bool:
    home_value = str((request.metadata or {}).get("HOME") or "").strip()
    codex_home_value = str(
        (request.metadata or {}).get("CODEX_HOME") or ""
    ).strip()
    workspace_id = str(request.workspace_id or "").strip()
    if not home_value or not codex_home_value or not workspace_id:
        return False

    expected_key = (home_value, workspace_id)
    changed = False
    for candidate in candidates:
        if str(getattr(candidate, "id", "") or "") == runtime_id:
            continue
        candidate_key = _host_session_shadow_candidate_key(
            candidate,
            owner_user_id=owner_user_id,
            surface=request.surface,
            pool_group=pool_group,
        )
        if candidate_key != expected_key:
            continue
        candidate_meta = dict(getattr(candidate, "extra_metadata", None) or {})
        if str(candidate_meta.get("shadowed_by_runtime_id") or "") == runtime_id:
            continue
        candidate_meta["shadowed_by_runtime_id"] = runtime_id
        candidate.extra_metadata = candidate_meta
        sync_runtime_registration_metadata(candidate)
        changed = True
    return changed


def _list_host_session_shadow_candidates(
    *,
    owner_user_id: str,
    surface: str,
    pool_group: str,
) -> dict[tuple[str, str], tuple[str, ...]]:
    from backend.app.models.runtime_environment import RuntimeEnvironment

    db = _get_host_session_shadow_db()
    try:
        candidates = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.user_id == owner_user_id,
                RuntimeEnvironment.auth_type == "host_session",
            )
            .all()
        )
        grouped: dict[tuple[str, str], list[str]] = {}
        for candidate in candidates:
            key = _host_session_shadow_candidate_key(
                candidate,
                owner_user_id=owner_user_id,
                surface=surface,
                pool_group=pool_group,
            )
            if key is not None:
                grouped.setdefault(key, []).append(str(candidate.id))
        return {
            key: tuple(sorted(runtime_ids))
            for key, runtime_ids in sorted(grouped.items())
        }
    finally:
        db.close()


def _reconcile_host_session_runtime_shadow(
    *,
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
    runtime_id: str,
    candidate_runtime_ids: tuple[str, ...],
) -> bool:
    if not candidate_runtime_ids:
        return False

    from backend.app.models.runtime_environment import RuntimeEnvironment

    db = _get_host_session_shadow_db()
    try:
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(RuntimeEnvironment.id == runtime_id)
            .first()
        )
        if runtime is None or str(runtime.user_id or "") != owner_user_id:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Host-session runtime unavailable during shadow reconciliation: "
                    f"{runtime_id}"
                ),
            )
        candidates = (
            db.query(RuntimeEnvironment)
            .filter(RuntimeEnvironment.id.in_(tuple(candidate_runtime_ids)))
            .all()
        )
        pool_group = request.pool_group or _default_pool_group_for_surface(
            request.surface
        )
        changed = _apply_host_session_shadow(
            candidates=candidates,
            owner_user_id=owner_user_id,
            request=request,
            runtime_id=runtime_id,
            pool_group=pool_group,
        )
        if changed:
            db.commit()
        return changed
    except Exception:
        if hasattr(db, "rollback"):
            db.rollback()
        raise
    finally:
        db.close()
