import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _codex_identity_from_result(result: Any) -> Dict[str, Any]:
    metadata = getattr(result, "agent_metadata", None)
    if not isinstance(metadata, dict):
        return {}
    identity = metadata.get("codex_account_identity")
    if isinstance(identity, dict):
        return dict(identity)
    dispatch_metadata = metadata.get("dispatch_metadata")
    if isinstance(dispatch_metadata, dict):
        identity = dispatch_metadata.get("codex_account_identity")
        if isinstance(identity, dict):
            return dict(identity)
    return {}


def _persist_codex_account_home_probe_result(
    runtime_id: str,
    result: Any,
) -> Dict[str, Any]:
    selected_runtime_id = str(runtime_id or "").strip()
    if not selected_runtime_id:
        raise HTTPException(
            status_code=400,
            detail="Codex account-home probe requires a runtime_id.",
        )

    from backend.app.services.codex_pool_health import (
        stamp_runtime_failure,
        stamp_runtime_probe_failure,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService
    from backend.app.services.codex_runtime_failure_classifier import (
        classify_codex_cli_runtime_failure,
        extract_codex_quota_reset_at,
    )

    service = CodexPoolService()
    if bool(getattr(result, "success", False)):
        service.report_runtime_success(selected_runtime_id)
        return {
            "success": True,
            "fault_kind": None,
            "error_code": None,
        }

    error_part = str(getattr(result, "error", None) or "").strip()
    output_part = str(getattr(result, "output", None) or "").strip()
    message = f"{error_part} {output_part}".strip() or "codex_probe_failed"
    classification = classify_codex_cli_runtime_failure(message)
    fault_kind = str(classification.get("fault_kind") or "runtime").strip()
    error_code = str(classification.get("error_code") or "runtime_error").strip()

    if fault_kind == "quota":
        service.report_quota_exhausted(
            selected_runtime_id,
            reset_at=extract_codex_quota_reset_at(message),
        )
    elif fault_kind == "auth":
        service.report_auth_failure(
            selected_runtime_id,
            error_code=error_code,
        )
    else:
        inconclusive_probe_errors = {
            "timeout",
            "runtime_error",
            "probe_transport_error",
            "codex_cli_panic",
            "token_refresh_persist_failed",
        }
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == selected_runtime_id,
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                )
                .first()
            )
            if runtime:
                metadata = dict(getattr(runtime, "extra_metadata", None) or {})
                if error_code not in inconclusive_probe_errors:
                    runtime.last_error_code = error_code
                    metadata = stamp_runtime_failure(
                        metadata,
                        error_code=error_code,
                        auth_type=str(getattr(runtime, "auth_type", "") or ""),
                        failure_scope_key=f"runtime:{selected_runtime_id}",
                    )
                runtime.extra_metadata = stamp_runtime_probe_failure(
                    metadata,
                    error_code=error_code,
                    returncode=int(getattr(result, "exit_code", 1) or 1),
                )
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception("Failed to persist Codex account-home probe failure")
        finally:
            db.close()

    return {
        "success": False,
        "fault_kind": fault_kind,
        "error_code": error_code,
    }


def _persist_codex_account_home_login_metadata(
    inputs: Dict[str, Any],
    observed_identity: Dict[str, Any],
) -> None:
    runtime_id = str(inputs.get("runtime_id") or "").strip()
    account_key = str(inputs.get("expected_account_key") or inputs.get("account_key") or "").strip()
    codex_home = str(inputs.get("expected_codex_home") or inputs.get("codex_home") or "").strip()
    if not any((runtime_id, account_key, codex_home)):
        return

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
            runtime_home = str(
                metadata.get("CODEX_HOME")
                or metadata.get("codex_home")
                or metadata.get("host_session_home")
                or ""
            ).strip()
            runtime_account_key = str(metadata.get("account_key") or "").strip()
            if account_key and runtime_account_key != account_key:
                continue
            if codex_home and runtime_home != codex_home:
                continue
            candidates.append((runtime, metadata))

        if len(candidates) != 1:
            db.rollback()
            return

        runtime, metadata = candidates[0]
        for key, value in observed_identity.items():
            if value is not None and key != "identity_error":
                metadata[key] = value
        metadata["last_account_home_login_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        metadata["last_account_home_login_state"] = "succeeded"
        metadata["probe_state"] = "unknown"
        metadata["last_probe_error_code"] = None
        metadata["last_probe_success_at"] = None
        metadata["last_probe_runtime_returncode"] = None
        metadata["last_probe_invalidated_by_login_at"] = metadata[
            "last_account_home_login_at"
        ]
        if str(getattr(runtime, "last_error_code", "") or "").strip().lower() in {
            "401",
            "403",
            "auth_failed",
            "invalid_grant",
            "stale_refresh_token",
        }:
            runtime.last_error_code = None
            runtime.cooldown_until = None
        runtime.extra_metadata = metadata
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Failed to persist Codex account-home login metadata")
    finally:
        if db is not None:
            db.close()


def _validate_codex_account_home_login_identity(
    inputs: Dict[str, Any],
    observed_identity: Optional[Dict[str, Any]] = None,
) -> None:
    codex_home = str(inputs.get("codex_home") or "").strip()
    if not codex_home:
        return
    expected_account_key = str(inputs.get("expected_account_key") or "").strip()
    expected_login_email = str(inputs.get("expected_login_email") or "").strip().lower()
    if not expected_account_key and not expected_login_email:
        return

    observed = observed_identity if isinstance(observed_identity, dict) else {}
    if observed:
        actual_account_key = str(observed.get("account_key") or "").strip()
        actual_login_email = str(observed.get("login_email") or "").strip().lower()
        if expected_account_key and actual_account_key == expected_account_key:
            return
        if not expected_account_key and expected_login_email and actual_login_email == expected_login_email:
            return
        if actual_account_key or actual_login_email:
            if expected_account_key and actual_account_key != expected_account_key:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Codex account-home login wrote a different account identity "
                        f"than the selected target: expected account_key={expected_account_key}, "
                        f"actual account_key={actual_account_key or 'unknown'}, "
                        f"actual login_email={actual_login_email or 'unknown'}."
                    ),
                )
            if expected_login_email and actual_login_email != expected_login_email:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Codex account-home login wrote a different login email "
                        f"than the selected target: expected login_email={expected_login_email}, "
                        f"actual login_email={actual_login_email or 'unknown'}."
                    ),
                )

    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )

    import time

    actual_account_key = ""
    actual_login_email = ""
    deadline = time.monotonic() + 5.0
    while True:
        actual = CodexAccountHomeAuthSourceService.metadata_for_codex_home(codex_home)
        actual_account_key = str(actual.get("account_key") or "").strip()
        actual_login_email = str(actual.get("login_email") or "").strip().lower()
        if expected_account_key and actual_account_key == expected_account_key:
            return
        if not expected_account_key and expected_login_email and actual_login_email == expected_login_email:
            return
        if actual_account_key or actual_login_email or time.monotonic() >= deadline:
            break
        time.sleep(0.25)

    if expected_account_key and actual_account_key != expected_account_key:
        raise HTTPException(
            status_code=409,
            detail=(
                "Codex account-home login wrote a different account identity "
                f"than the selected target: expected account_key={expected_account_key}, "
                f"actual account_key={actual_account_key or 'unknown'}, "
                f"actual login_email={actual_login_email or 'unknown'}."
            ),
        )
    if expected_login_email and actual_login_email != expected_login_email:
        raise HTTPException(
            status_code=409,
            detail=(
                "Codex account-home login wrote a different login email "
                f"than the selected target: expected login_email={expected_login_email}, "
                f"actual login_email={actual_login_email or 'unknown'}."
            ),
        )
