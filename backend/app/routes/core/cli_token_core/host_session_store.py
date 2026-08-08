import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from backend.app.routes.core.cli_token_core.host_session_metadata import (
    _clear_stale_shadow_marker,
    _coerce_json_dict,
    _default_pool_group_for_surface,
    _effective_host_session_pool_enabled,
    _prepare_host_session_runtime_metadata,
    _stable_host_session_runtime_id,
)
from backend.app.routes.core.cli_token_core.schemas import RegisterHostSessionRuntimeRequest
from backend.app.routes.core.cli_token_core.host_session_shadow import (
    _apply_host_session_shadow,
)
from backend.app.services.runtime_route_registration import (
    attach_runtime_registration_metadata,
    sync_runtime_registration_metadata,
)

logger = logging.getLogger(__name__)


def _get_host_session_db():
    try:
        from backend.app.database.session import get_db_postgres as get_db
    except ImportError:
        try:
            from backend.app.database import get_db_postgres as get_db
        except ImportError:
            from mindscape.di.providers import get_db_session as get_db
    return next(get_db())


def _upsert_host_session_runtime(
    *,
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
    reconcile_shadow: bool = True,
) -> dict[str, Any]:
    from backend.app.models.runtime_environment import RuntimeEnvironment

    db = _get_host_session_db()
    try:
        try:
            runtime_id = _stable_host_session_runtime_id(
                owner_user_id=owner_user_id,
                surface=request.surface,
                client_id=request.client_id,
                metadata=request.metadata,
                workspace_id=request.workspace_id,
                explicit_runtime_id=request.runtime_id,
            )
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(RuntimeEnvironment.id == runtime_id)
                .first()
            )
            metadata = dict(request.metadata or {})
            metadata.update(
                {
                    "surface": request.surface,
                    "registered_via": "host_session_bridge",
                    "last_workspace_id": request.workspace_id,
                    "last_client_id": request.client_id,
                }
            )
            pool_group = request.pool_group or _default_pool_group_for_surface(request.surface)
            runtime_name = (
                str(request.runtime_name or "").strip()
                or f"{request.surface} host session"
            )
            config_url = f"/settings/runtime-environments/{runtime_id}"

            if runtime is None:
                runtime_metadata, _ = _prepare_host_session_runtime_metadata(
                    existing_metadata={},
                    incoming_metadata=metadata,
                )
                effective_pool_enabled = _effective_host_session_pool_enabled(
                    runtime_metadata,
                    requested_pool_enabled=request.pool_enabled,
                )
                runtime = RuntimeEnvironment(
                    id=runtime_id,
                    user_id=owner_user_id,
                    name=runtime_name,
                    description=f"Auto-registered host session for {request.surface}",
                    icon="terminal",
                    config_url=config_url,
                    auth_type="host_session",
                    auth_config={},
                    extra_metadata=runtime_metadata,
                    status="active",
                    auth_status="connected",
                    is_default=False,
                    supports_dispatch=True,
                    supports_cell=True,
                    recommended_for_dispatch=False,
                    pool_group=pool_group,
                    pool_enabled=effective_pool_enabled,
                    pool_priority=request.pool_priority,
                )
                db.add(runtime)
            else:
                if runtime.user_id != owner_user_id:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Runtime id collision for '{runtime_id}' while registering "
                            f"{request.surface} host session"
                        ),
                    )
                runtime.name = runtime_name
                runtime.description = f"Auto-registered host session for {request.surface}"
                runtime.icon = runtime.icon or "terminal"
                runtime.config_url = config_url
                runtime.auth_type = "host_session"
                runtime.auth_config = {}
                runtime.extra_metadata, reset_runtime_health = (
                    _prepare_host_session_runtime_metadata(
                        existing_metadata=runtime.extra_metadata,
                        incoming_metadata=metadata,
                    )
                )
                effective_pool_enabled = _effective_host_session_pool_enabled(
                    dict(runtime.extra_metadata or {}),
                    requested_pool_enabled=request.pool_enabled,
                )
                runtime.extra_metadata = _clear_stale_shadow_marker(
                    dict(runtime.extra_metadata or {}),
                    pool_enabled=effective_pool_enabled,
                )
                if reset_runtime_health:
                    runtime.cooldown_until = None
                    runtime.last_error_code = None
                runtime.status = "active"
                runtime.auth_status = "connected"
                runtime.pool_group = pool_group
                runtime.pool_enabled = effective_pool_enabled
                runtime.pool_priority = request.pool_priority

            if reconcile_shadow:
                candidates = (
                    db.query(RuntimeEnvironment)
                    .filter(
                        RuntimeEnvironment.user_id == owner_user_id,
                        RuntimeEnvironment.auth_type == "host_session",
                    )
                    .all()
                )
                _apply_host_session_shadow(
                    candidates=candidates,
                    owner_user_id=owner_user_id,
                    request=request,
                    runtime_id=runtime.id,
                    pool_group=pool_group,
                )

            sync_runtime_registration_metadata(runtime)
            db.commit()
            db.refresh(runtime)
            payload = attach_runtime_registration_metadata(
                runtime.to_dict(include_sensitive=False)
            )
            payload["runtime_id"] = runtime.id
            payload["owner_user_id"] = owner_user_id
            return payload
        except Exception:
            if not hasattr(db, "execute"):
                raise
            if hasattr(db, "rollback"):
                db.rollback()
            logger.warning(
                "Host-session runtime ORM upsert failed for workspace=%s surface=%s; falling back to raw SQL",
                request.workspace_id,
                request.surface,
                exc_info=True,
            )
            return _upsert_host_session_runtime_sql(
                db=db,
                owner_user_id=owner_user_id,
                request=request,
            )
    finally:
        db.close()


def _upsert_host_session_runtime_sql(
    *,
    db: Any,
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    runtime_id = _stable_host_session_runtime_id(
        owner_user_id=owner_user_id,
        surface=request.surface,
        client_id=request.client_id,
        metadata=request.metadata,
        workspace_id=request.workspace_id,
        explicit_runtime_id=request.runtime_id,
    )
    metadata = dict(request.metadata or {})
    metadata.update(
        {
            "surface": request.surface,
            "registered_via": "host_session_bridge",
            "last_workspace_id": request.workspace_id,
            "last_client_id": request.client_id,
        }
    )
    pool_group = request.pool_group or _default_pool_group_for_surface(request.surface)
    runtime_name = (
        str(request.runtime_name or "").strip()
        or f"{request.surface} host session"
    )
    config_url = f"/settings/runtime-environments/{runtime_id}"

    existing = (
        db.execute(
            text(
                """
                SELECT id, user_id, extra_metadata
                FROM runtime_environments
                WHERE id = :runtime_id
                LIMIT 1
                """
            ),
            {"runtime_id": runtime_id},
        )
        .mappings()
        .first()
    )
    if existing and str(existing.get("user_id")) != owner_user_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Runtime id collision for '{runtime_id}' while registering "
                f"{request.surface} host session"
            ),
        )

    merged_metadata, reset_runtime_health = _prepare_host_session_runtime_metadata(
        existing_metadata=existing.get("extra_metadata") if existing else {},
        incoming_metadata=metadata,
    )
    effective_pool_enabled = _effective_host_session_pool_enabled(
        merged_metadata,
        requested_pool_enabled=request.pool_enabled,
    )
    merged_metadata = _clear_stale_shadow_marker(
        merged_metadata,
        pool_enabled=effective_pool_enabled,
    )
    registration_payload = attach_runtime_registration_metadata(
        {
            "id": runtime_id,
            "name": runtime_name,
            "status": "active",
            "auth_type": "host_session",
            "metadata": merged_metadata,
            "pool_group": pool_group,
            "pool_enabled": effective_pool_enabled,
        }
    )
    auth_config_json = json.dumps({})
    metadata_json = json.dumps(registration_payload["metadata"])

    payload = (
        db.execute(
            text(
                """
                INSERT INTO runtime_environments (
                    id, user_id, name, description, icon, config_url, auth_type,
                    auth_config, status, is_default, auth_status, supports_dispatch,
                    supports_cell, recommended_for_dispatch, extra_metadata, pool_group,
                    pool_enabled, pool_priority, last_error_code, created_at, updated_at
                ) VALUES (
                    :id, :user_id, :name, :description, :icon, :config_url,
                    'host_session', CAST(:auth_config AS JSONB), 'active', false,
                    'connected', true, true, false, CAST(:extra_metadata AS JSONB),
                    :pool_group, :pool_enabled, :pool_priority, NULL, NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    icon = EXCLUDED.icon,
                    config_url = EXCLUDED.config_url,
                    auth_type = 'host_session',
                    auth_config = CAST(:auth_config AS JSONB),
                    status = 'active',
                    auth_status = 'connected',
                    supports_dispatch = true,
                    supports_cell = true,
                    recommended_for_dispatch = false,
                    extra_metadata = CAST(:extra_metadata AS JSONB),
                    pool_group = EXCLUDED.pool_group,
                    pool_enabled = EXCLUDED.pool_enabled,
                    pool_priority = EXCLUDED.pool_priority,
                    cooldown_until = CASE
                        WHEN :reset_runtime_health THEN NULL
                        ELSE runtime_environments.cooldown_until
                    END,
                    last_error_code = CASE
                        WHEN :reset_runtime_health THEN NULL
                        ELSE runtime_environments.last_error_code
                    END,
                    updated_at = NOW()
                RETURNING
                    id, name, description, icon, config_url, auth_type, status,
                    is_default, supports_dispatch, supports_cell,
                    recommended_for_dispatch, extra_metadata, auth_status, pool_group,
                    pool_enabled, pool_priority, cooldown_until, last_used_at,
                    last_error_code, created_at, updated_at
                """
            ),
            {
                "id": runtime_id,
                "user_id": owner_user_id,
                "name": runtime_name,
                "description": f"Auto-registered host session for {request.surface}",
                "icon": "terminal",
                "config_url": config_url,
                "auth_config": auth_config_json,
                "extra_metadata": metadata_json,
                "pool_group": pool_group,
                "pool_enabled": effective_pool_enabled,
                "pool_priority": request.pool_priority,
                "reset_runtime_health": reset_runtime_health,
            },
        )
        .mappings()
        .first()
    )
    db.commit()
    if not payload:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upsert host-session runtime {runtime_id}",
        )
    return attach_runtime_registration_metadata(
        {
            "id": payload["id"],
            "runtime_id": payload["id"],
            "name": payload["name"],
            "description": payload["description"],
            "icon": payload["icon"],
            "config_url": payload["config_url"],
            "auth_type": payload["auth_type"],
            "status": payload["status"],
            "is_default": payload["is_default"],
            "supports_dispatch": payload["supports_dispatch"],
            "supports_cell": payload["supports_cell"],
            "recommended_for_dispatch": payload["recommended_for_dispatch"],
            "metadata": _coerce_json_dict(payload.get("extra_metadata")),
            "auth_status": payload["auth_status"],
            "pool_group": payload["pool_group"],
            "pool_enabled": payload["pool_enabled"],
            "pool_priority": payload["pool_priority"],
            "cooldown_until": (
                payload["cooldown_until"].isoformat()
                if payload.get("cooldown_until")
                else None
            ),
            "last_used_at": (
                payload["last_used_at"].isoformat()
                if payload.get("last_used_at")
                else None
            ),
            "last_error_code": payload["last_error_code"],
            "created_at": payload["created_at"].isoformat() if payload.get("created_at") else None,
            "updated_at": payload["updated_at"].isoformat() if payload.get("updated_at") else None,
            "owner_user_id": owner_user_id,
        }
    )
