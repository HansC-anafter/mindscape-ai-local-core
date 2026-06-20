"""Runtime router, DB audit, and Codex probe helpers for quota preflight."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any


async def _resolve_bundle(
    workspace_id: str,
    excluded_runtime_ids: set[str],
    excluded_quota_scope_keys: set[str],
) -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        resolve_codex_pool_runtime_bundle,
    )

    return await resolve_codex_pool_runtime_bundle(
        workspace_id=workspace_id,
        lease_owner_type="e2e_preflight",
        lease_owner_id=workspace_id,
        excluded_runtime_ids=excluded_runtime_ids,
        excluded_quota_scope_keys=excluded_quota_scope_keys,
        fail_closed_session_lease=False,
        record_runtime_lease=False,
    )


async def _runtime_pool_summary() -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        summarize_codex_pool_runtime_health,
    )

    return await summarize_codex_pool_runtime_health()


async def _report_runtime_fault(
    *,
    runtime_id: str,
    workspace_id: str,
    error_text: str,
) -> dict[str, str]:
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_fault,
    )
    from backend.app.services.codex_runtime_failure_classifier import (
        classify_codex_cli_runtime_failure,
    )

    classification = classify_codex_cli_runtime_failure(error_text)
    fault_kind = str(classification.get("fault_kind") or "runtime").strip()
    error_code = str(classification.get("error_code") or "runtime_error").strip()
    if fault_kind == "quota":
        await report_codex_pool_runtime_fault(
            runtime_id=runtime_id,
            fault_kind="quota",
            workspace_id=workspace_id,
            error_code=error_code,
            error_text=error_text,
        )
        return {"fault_kind": "quota", "error_code": error_code}
    if fault_kind == "auth":
        await report_codex_pool_runtime_fault(
            runtime_id=runtime_id,
            fault_kind="auth",
            workspace_id=workspace_id,
            error_code=error_code,
        )
        return {"fault_kind": "auth", "error_code": error_code}
    return {"fault_kind": "runtime", "error_code": error_code}


async def _report_runtime_success(*, runtime_id: str) -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_success,
    )

    return await report_codex_pool_runtime_success(runtime_id=runtime_id)


def _direct_account_home_runtime_bundles(*, required_login_email: str = "") -> list[dict[str, Any]]:
    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )
    from backend.app.services.codex_pool_health import (
        is_pool_member_runtime_metadata,
        read_health_metadata,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

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
        bundles: list[dict[str, Any]] = []
        for runtime in runtimes:
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            auth_type = str(getattr(runtime, "auth_type", "") or "").strip()
            health = read_health_metadata(metadata, auth_type=auth_type)
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            if not is_pool_member_runtime_metadata(metadata, auth_type=auth_type):
                continue
            login_email = str(metadata.get("login_email") or "").strip().lower()
            if required_login_email and login_email != required_login_email:
                continue
            env = {
                key: str(metadata.get(key) or "").strip()
                for key in (
                    "CODEX_HOME",
                    "HOME",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                    "XDG_STATE_HOME",
                )
                if str(metadata.get(key) or "").strip()
            }
            codex_home = str(env.get("CODEX_HOME") or "").strip()
            if codex_home:
                metadata.update(
                    CodexAccountHomeAuthSourceService.metadata_for_codex_home(
                        codex_home,
                        metadata=metadata,
                    )
                )
            runtime_id = str(getattr(runtime, "id", "") or "").strip()
            account_key = str(metadata.get("account_key") or "").strip()
            quota_scope_key = (
                f"account:{account_key}"
                if account_key
                else str(metadata.get("quota_scope_key") or "").strip()
                or f"runtime:{runtime_id}"
            )
            try:
                auth_mtime_ns = (
                    Path(str(env.get("CODEX_HOME") or "")) / "auth.json"
                ).stat().st_mtime_ns
            except OSError:
                auth_mtime_ns = 0
            bundles.append(
                {
                    "selected_runtime_id": runtime_id,
                    "runtime_auth_type": auth_type,
                    "env": env,
                    "quota_scope_key": quota_scope_key,
                    "runtime_account_identity": {
                        "login_email": login_email or None,
                        "account_key": account_key or None,
                        "auth_account_id": str(
                            metadata.get("auth_account_id") or ""
                        ).strip()
                        or None,
                        "auth_chatgpt_user_id": str(
                            metadata.get("auth_chatgpt_user_id") or ""
                        ).strip()
                        or None,
                    },
                    "cooldown_until": str(getattr(runtime, "cooldown_until", "") or "")
                    or None,
                    "last_error_code": str(getattr(runtime, "last_error_code", "") or "")
                    or None,
                    "db_probe_state": str(metadata.get("probe_state") or "").strip()
                    or None,
                    "db_last_probe_error_code": str(
                        metadata.get("last_probe_error_code") or ""
                    ).strip()
                    or None,
                    "db_last_probe_success_at": str(
                        metadata.get("last_probe_success_at") or ""
                    ).strip()
                    or None,
                    "auth_mtime_ns": auth_mtime_ns,
                }
            )
        sorted_bundles = sorted(
            bundles,
            key=lambda item: (
                str(
                    (item.get("runtime_account_identity") or {}).get("login_email")
                    or ""
                ),
                -int(item.get("auth_mtime_ns") or 0),
                str(item.get("selected_runtime_id") or ""),
            ),
        )
        deduped: dict[str, dict[str, Any]] = {}
        for bundle in sorted_bundles:
            scope_key = str(bundle.get("quota_scope_key") or "").strip()
            deduped.setdefault(scope_key or str(bundle.get("selected_runtime_id")), bundle)
        return list(deduped.values())
    finally:
        db.close()


async def _probe_bundle(
    *,
    bundle: dict[str, Any],
    timeout_seconds: float,
    stall_timeout_seconds: float,
) -> dict[str, Any]:
    from backend.app.services.external_agents.bridge.codex_cli_runner import (
        resolve_codex_cli_binary,
        resolve_codex_cli_cwd,
        run_codex_cli_subprocess,
    )
    from backend.app.services.llm.core_llm import _merge_codex_env
    from backend.app.shared.llm_utils import extract_json_from_text

    binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
    cwd = resolve_codex_cli_cwd(os.environ.get("HOST_PROJECT_PATH", "").strip())
    with tempfile.NamedTemporaryFile(
        prefix="codex_pool_quota_probe_",
        suffix=".txt",
        delete=False,
    ) as tmp:
        last_message_path = tmp.name

    cmd = [
        binary,
        "-c",
        'model_reasoning_effort="low"',
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        last_message_path,
        'Return ONLY valid JSON: {"codex_pool_quota_probe": true}',
    ]
    try:
        result = await run_codex_cli_subprocess(
            cmd=cmd,
            cwd=cwd,
            env=_merge_codex_env(bundle.get("env")),
            last_message_path=last_message_path,
            execution_id=f"codex-pool-quota-probe-{uuid.uuid4()}",
            timeout=timeout_seconds,
            stall_timeout=stall_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        return {
            "success": False,
            "error": str(exc).strip() or "codex_cli quota probe timed out",
        }
    finally:
        try:
            os.unlink(last_message_path)
        except OSError:
            pass

    output_text = str(result.output_text or "").strip()
    parsed = extract_json_from_text(output_text)
    success = (
        result.returncode == 0
        and isinstance(parsed, dict)
        and parsed.get("codex_pool_quota_probe") is True
    )
    return {
        "success": success,
        "returncode": result.returncode,
        "output": output_text[:500],
        "error": (
            result.synthesized_error
            or result.combined_output
            or result.stderr_text
            or ""
        )[:1000],
    }
