from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from .account_home_paths import _account_home_env
from .schemas import CodexAccountHomeTarget, WorkspaceAgentAuthActionRequest


def _iso_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _list_codex_account_home_targets() -> List[CodexAccountHomeTarget]:
    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )
    from backend.app.services.codex_pool_health import (
        read_health_metadata,
        read_probe_metadata,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    auth_sources = CodexAccountHomeAuthSourceService()
    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    try:
        runtimes = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
                RuntimeEnvironment.auth_type.in_(("host_session", "none")),
            )
            .all()
        )
        targets: List[CodexAccountHomeTarget] = []
        changed = False
        for runtime in runtimes:
            auth_type = str(getattr(runtime, "auth_type", "") or "")
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(metadata, auth_type=auth_type)
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            codex_home = str(
                metadata.get("CODEX_HOME")
                or metadata.get("codex_home")
                or metadata.get("host_session_home")
                or ""
            ).strip()
            if not codex_home:
                continue

            auth_metadata = auth_sources.metadata_for_codex_home(
                codex_home,
                metadata=metadata,
            )
            if auth_metadata:
                metadata.update(auth_metadata)
                runtime.extra_metadata = metadata
                changed = True
            identity_details = auth_sources.identity_details_for_codex_home(codex_home)
            if identity_details:
                metadata.update(identity_details)
                runtime.extra_metadata = metadata
                changed = True

            probe = read_probe_metadata(metadata)
            targets.append(
                CodexAccountHomeTarget(
                    runtime_id=str(getattr(runtime, "id", "") or ""),
                    login_email=str(metadata.get("login_email") or "").strip().lower()
                    or None,
                    account_key=str(metadata.get("account_key") or "").strip()
                    or None,
                    account_scope_type=str(metadata.get("account_scope_type") or "").strip()
                    or None,
                    account_scope_label=str(metadata.get("account_scope_label") or "").strip()
                    or None,
                    account_scope_role=str(metadata.get("account_scope_role") or "").strip()
                    or None,
                    account_plan_type=str(metadata.get("account_plan_type") or "").strip()
                    or None,
                    account_organization_id=str(
                        metadata.get("account_organization_id") or ""
                    ).strip()
                    or None,
                    account_organization_title=str(
                        metadata.get("account_organization_title") or ""
                    ).strip()
                    or None,
                    account_organization_count=metadata.get("account_organization_count"),
                    codex_home=codex_home,
                    auth_json_path=str(metadata.get("auth_source_path") or "").strip()
                    or None,
                    auth_mtime_ns=str(
                        metadata.get("auth_mtime_ns")
                        or metadata.get("codex_auth_mtime_ns")
                        or ""
                    ).strip()
                    or None,
                    auth_size=str(
                        metadata.get("auth_size") or metadata.get("codex_auth_size") or ""
                    ).strip()
                    or None,
                    has_access=bool(metadata.get("auth_source_has_access")),
                    has_refresh=bool(metadata.get("auth_source_has_refresh")),
                    probe_state=str(probe.get("probe_state") or "").strip()
                    or None,
                    last_probe_error_code=probe.get("last_probe_error_code"),
                    last_probe_success_at=probe.get("last_probe_success_at"),
                    cooldown_until=_iso_value(getattr(runtime, "cooldown_until", None)),
                    last_error_code=str(getattr(runtime, "last_error_code", "") or "").strip()
                    or None,
                )
            )
        if changed:
            db.commit()
        else:
            db.rollback()
        return sorted(
            targets,
            key=lambda target: (
                target.login_email or "",
                target.account_key or "",
                target.runtime_id,
            ),
        )
    finally:
        db.close()


def _resolve_codex_account_home_inputs(
    payload: Optional[WorkspaceAgentAuthActionRequest],
) -> Dict[str, Any]:
    if payload is None:
        return {}

    runtime_id = str(payload.runtime_id or "").strip()
    login_email = str(payload.login_email or "").strip().lower()
    account_key = str(payload.account_key or "").strip()
    codex_home = str(payload.codex_home or "").strip()
    if codex_home and not any((runtime_id, login_email, account_key)):
        return {
            "codex_home": codex_home,
            "expected_codex_home": codex_home,
            "env": _account_home_env(codex_home),
        }
    if not any((runtime_id, login_email, account_key)):
        return {}

    from backend.app.services.codex_pool_health import read_health_metadata
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    db = None
    try:
        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        query = db.query(RuntimeEnvironment).filter(
            RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
            RuntimeEnvironment.pool_enabled.is_(True),
            RuntimeEnvironment.auth_type.in_(("host_session", "none")),
        )
        if runtime_id:
            query = query.filter(RuntimeEnvironment.id == runtime_id)
        candidates = []
        for runtime in query.all():
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(
                metadata,
                auth_type=str(getattr(runtime, "auth_type", "") or ""),
            )
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            if login_email and str(metadata.get("login_email") or "").strip().lower() != login_email:
                continue
            if account_key and str(metadata.get("account_key") or "").strip() != account_key:
                continue
            if codex_home:
                runtime_home = str(
                    metadata.get("CODEX_HOME") or metadata.get("codex_home") or ""
                ).strip()
                if runtime_home != codex_home:
                    continue
            candidates.append((runtime, metadata))
    finally:
        db.close()

    if not candidates:
        raise HTTPException(status_code=404, detail="No matching Codex account-home runtime")
    if len(candidates) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Multiple Codex account-home runtimes match; provide runtime_id "
                "or account_key to disambiguate"
            ),
        )

    runtime, metadata = candidates[0]
    codex_home = str(metadata.get("CODEX_HOME") or metadata.get("codex_home") or "").strip()
    if not codex_home:
        raise HTTPException(status_code=409, detail="Matched runtime has no CODEX_HOME")
    return {
        "runtime_id": str(getattr(runtime, "id", "") or ""),
        "login_email": str(metadata.get("login_email") or "").strip().lower(),
        "account_key": str(metadata.get("account_key") or "").strip(),
        "codex_home": codex_home,
        "expected_login_email": login_email
        or str(metadata.get("login_email") or "").strip().lower(),
        "expected_account_key": account_key
        or str(metadata.get("account_key") or "").strip(),
        "expected_codex_home": codex_home,
        "env": _account_home_env(codex_home),
    }
