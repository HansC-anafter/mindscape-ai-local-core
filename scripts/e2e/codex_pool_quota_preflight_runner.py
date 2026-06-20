"""Preflight runner flows for Codex quota checks."""

from __future__ import annotations

import argparse
from typing import Any

from codex_pool_quota_preflight_env import (
    _codex_cli_compatibility_check,
    _env_keys,
    _host_session_env_class,
    _normalized_required_login_email,
    _with_cli_evidence,
)
from codex_pool_quota_preflight_runtime import (
    _direct_account_home_runtime_bundles,
    _probe_bundle,
    _report_runtime_fault,
    _report_runtime_success,
    _resolve_bundle,
    _runtime_pool_summary,
)


async def run_account_home_audit(args: argparse.Namespace) -> dict[str, Any]:
    required_login_email = _normalized_required_login_email(args)
    target_successes = max(1, int(args.target_successes or 1))
    cli_evidence = _codex_cli_compatibility_check()
    if not bool(cli_evidence.get("codex_cli_compatible")):
        return _with_cli_evidence(
            {
                "status": "blocked",
                "workspace_id": args.workspace_id,
                "target_successes": target_successes,
                "successful_runtime_count": 0,
                "successful_quota_scope_count": 0,
                "successful_runtime_ids": [],
                "successful_quota_scope_keys": [],
                "runtime_pool_summary": await _runtime_pool_summary(),
                "attempts": [],
                "audit_mode": "all_account_homes_ignore_cooldown",
            },
            cli_evidence,
        )

    bundles = _direct_account_home_runtime_bundles(
        required_login_email=required_login_email,
    )
    attempts: list[dict[str, Any]] = []
    successful_runtime_ids: list[str] = []
    successful_quota_scope_keys: list[str] = []
    successful_quota_scope_key_set: set[str] = set()
    for index, bundle in enumerate(bundles[: max(1, args.max_runtime_probes)]):
        runtime_id = str(bundle.get("selected_runtime_id") or "").strip()
        runtime_identity = bundle.get("runtime_account_identity")
        if not isinstance(runtime_identity, dict):
            runtime_identity = {}
        attempt: dict[str, Any] = {
            "attempt": index + 1,
            "selected_runtime_id": runtime_id or None,
            "runtime_account_identity": runtime_identity,
            "runtime_auth_type": bundle.get("runtime_auth_type"),
            "quota_scope_key": bundle.get("quota_scope_key"),
            "env_keys": _env_keys(bundle),
            "host_session_env_class": _host_session_env_class(bundle),
            "db_cooldown_until": bundle.get("cooldown_until"),
            "db_last_error_code": bundle.get("last_error_code"),
            "db_probe_state": bundle.get("db_probe_state"),
            "db_last_probe_error_code": bundle.get("db_last_probe_error_code"),
            "db_last_probe_success_at": bundle.get("db_last_probe_success_at"),
            "auth_mtime_ns": bundle.get("auth_mtime_ns"),
        }
        probe = await _probe_bundle(
            bundle=bundle,
            timeout_seconds=args.timeout_seconds,
            stall_timeout_seconds=args.stall_timeout_seconds,
        )
        attempt["probe"] = probe
        if probe.get("success"):
            attempt["status"] = "available"
            attempt["success_report"] = await _report_runtime_success(
                runtime_id=runtime_id,
            )
            successful_runtime_ids.append(runtime_id)
            quota_scope_key = str(bundle.get("quota_scope_key") or "").strip() or (
                f"runtime:{runtime_id}"
            )
            attempt["counted_quota_scope_key"] = quota_scope_key
            if quota_scope_key and quota_scope_key not in successful_quota_scope_key_set:
                successful_quota_scope_keys.append(quota_scope_key)
                successful_quota_scope_key_set.add(quota_scope_key)
        else:
            error_text = str(probe.get("error") or probe.get("output") or "").strip()
            fault_result = await _report_runtime_fault(
                runtime_id=runtime_id,
                workspace_id=args.workspace_id,
                error_text=error_text,
            )
            attempt.update({"status": "failed", **fault_result})
        attempts.append(attempt)

    final_status = (
        "available" if len(successful_quota_scope_key_set) >= target_successes else "failed"
    )
    return _with_cli_evidence(
        {
            "status": final_status,
            "workspace_id": args.workspace_id,
            "target_successes": target_successes,
            "successful_runtime_count": len(successful_runtime_ids),
            "successful_quota_scope_count": len(successful_quota_scope_key_set),
            "successful_runtime_ids": successful_runtime_ids,
            "successful_quota_scope_keys": successful_quota_scope_keys,
            "runtime_pool_summary": await _runtime_pool_summary(),
            "attempts": attempts,
            "audit_mode": "all_account_homes_ignore_cooldown",
            "audited_runtime_count": len(attempts),
        },
        cli_evidence,
    )


async def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    if bool(getattr(args, "audit_all_account_homes", False)):
        return await run_account_home_audit(args)

    excluded_runtime_ids: set[str] = {
        str(runtime_id or "").strip()
        for runtime_id in (args.exclude_runtime_id or [])
        if str(runtime_id or "").strip()
    }
    target_successes = max(1, int(args.target_successes or 1))
    cli_evidence = _codex_cli_compatibility_check()
    if not bool(cli_evidence.get("codex_cli_compatible")):
        return _with_cli_evidence(
            {
                "status": "blocked",
                "workspace_id": args.workspace_id,
                "target_successes": target_successes,
                "successful_runtime_count": 0,
                "successful_quota_scope_count": 0,
                "successful_runtime_ids": [],
                "successful_quota_scope_keys": [],
                "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                "runtime_pool_summary": await _runtime_pool_summary(),
                "attempts": [],
            },
            cli_evidence,
        )
    attempts: list[dict[str, Any]] = []
    successful_runtime_ids: list[str] = []
    successful_quota_scope_keys: list[str] = []
    successful_quota_scope_key_set: set[str] = set()
    excluded_quota_scope_keys: set[str] = set()
    for index in range(max(1, args.max_runtime_probes)):
        bundle = await _resolve_bundle(
            args.workspace_id,
            excluded_runtime_ids,
            excluded_quota_scope_keys,
        )
        pool_summary = await _runtime_pool_summary()
        pool_error = str(bundle.get("error") or bundle.get("warning") or "").strip()
        runtime_id = str(bundle.get("selected_runtime_id") or "").strip()
        runtime_identity = bundle.get("runtime_account_identity")
        if not isinstance(runtime_identity, dict):
            runtime_identity = {}
        attempt: dict[str, Any] = {
            "attempt": index + 1,
            "selected_runtime_id": runtime_id or None,
            "runtime_account_identity": runtime_identity,
            "preferred_runtime_id": bundle.get("preferred_runtime_id"),
            "auth_mode": bundle.get("auth_mode"),
            "runtime_auth_type": bundle.get("runtime_auth_type"),
            "available_runtime_count": bundle.get("available_runtime_count"),
            "available_quota_scope_count": bundle.get("available_quota_scope_count"),
            "quota_scope_key": bundle.get("quota_scope_key"),
            "env_keys": _env_keys(bundle),
            "host_session_env_class": _host_session_env_class(bundle),
            "policy_mode": bundle.get("policy_mode"),
            "requested_workspace_id": bundle.get("requested_workspace_id"),
            "effective_workspace_id": bundle.get("effective_workspace_id"),
            "auth_workspace_id": bundle.get("auth_workspace_id"),
            "source_workspace_id": bundle.get("source_workspace_id"),
            "selection_reason": bundle.get("selection_reason"),
            "selection_trace": bundle.get("selection_trace") or [],
            "admission": bundle.get("admission"),
            "runtime_pool_summary": pool_summary,
        }
        if pool_error:
            attempt.update({"status": "blocked", "error": pool_error})
            attempts.append(attempt)
            return _with_cli_evidence(
                {
                    "status": "blocked",
                    "workspace_id": args.workspace_id,
                    "target_successes": target_successes,
                    "successful_runtime_count": len(successful_runtime_ids),
                    "successful_quota_scope_count": len(successful_quota_scope_key_set),
                    "successful_runtime_ids": successful_runtime_ids,
                    "successful_quota_scope_keys": successful_quota_scope_keys,
                    "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                    "runtime_pool_summary": pool_summary,
                    "attempts": attempts,
                },
                cli_evidence,
            )
        if not runtime_id:
            attempt.update({"status": "blocked", "error": "missing selected_runtime_id"})
            attempts.append(attempt)
            return _with_cli_evidence(
                {
                    "status": "blocked",
                    "workspace_id": args.workspace_id,
                    "target_successes": target_successes,
                    "successful_runtime_count": len(successful_runtime_ids),
                    "successful_quota_scope_count": len(successful_quota_scope_key_set),
                    "successful_runtime_ids": successful_runtime_ids,
                    "successful_quota_scope_keys": successful_quota_scope_keys,
                    "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                    "runtime_pool_summary": pool_summary,
                    "attempts": attempts,
                },
                cli_evidence,
            )

        required_login_email = _normalized_required_login_email(args)
        if required_login_email:
            selected_login_email = str(
                runtime_identity.get("login_email") or ""
            ).strip().lower()
            attempt["required_login_email"] = required_login_email
            if selected_login_email != required_login_email:
                attempt.update(
                    {
                        "status": "identity_mismatch",
                        "error": "selected Codex runtime login email does not match required_login_email",
                        "selected_login_email": selected_login_email or None,
                    }
                )
                attempts.append(attempt)
                excluded_runtime_ids.add(runtime_id)
                continue

        probe = await _probe_bundle(
            bundle=bundle,
            timeout_seconds=args.timeout_seconds,
            stall_timeout_seconds=args.stall_timeout_seconds,
        )
        attempt["probe"] = probe
        if probe.get("success"):
            attempt["status"] = "available"
            attempt["success_report"] = await _report_runtime_success(
                runtime_id=runtime_id,
            )
            attempts.append(attempt)
            successful_runtime_ids.append(runtime_id)
            quota_scope_key = str(bundle.get("quota_scope_key") or "").strip() or (
                f"runtime:{runtime_id}"
            )
            attempt["counted_quota_scope_key"] = quota_scope_key
            if quota_scope_key and quota_scope_key not in successful_quota_scope_key_set:
                successful_quota_scope_keys.append(quota_scope_key)
                successful_quota_scope_key_set.add(quota_scope_key)
                excluded_quota_scope_keys.add(quota_scope_key)
            excluded_runtime_ids.add(runtime_id)
            if (
                len(successful_quota_scope_key_set) >= target_successes
                and not args.continue_after_success
            ):
                return _with_cli_evidence(
                    {
                        "status": "available",
                        "workspace_id": args.workspace_id,
                        "target_successes": target_successes,
                        "successful_runtime_count": len(successful_runtime_ids),
                        "successful_quota_scope_count": len(successful_quota_scope_key_set),
                        "successful_runtime_ids": successful_runtime_ids,
                        "successful_quota_scope_keys": successful_quota_scope_keys,
                        "selected_runtime_id": runtime_id,
                        "initial_excluded_runtime_ids": sorted(
                            args.exclude_runtime_id or []
                        ),
                        "runtime_pool_summary": pool_summary,
                        "attempts": attempts,
                    },
                    cli_evidence,
                )
            continue

        error_text = str(probe.get("error") or probe.get("output") or "").strip()
        fault_result = await _report_runtime_fault(
            runtime_id=runtime_id,
            workspace_id=args.workspace_id,
            error_text=error_text,
        )
        attempt.update({"status": "failed", **fault_result})
        attempts.append(attempt)
        excluded_runtime_ids.add(runtime_id)

    final_status = (
        "available" if len(successful_quota_scope_key_set) >= target_successes else "failed"
    )
    return _with_cli_evidence(
        {
            "status": final_status,
            "workspace_id": args.workspace_id,
            "target_successes": target_successes,
            "successful_runtime_count": len(successful_runtime_ids),
            "successful_quota_scope_count": len(successful_quota_scope_key_set),
            "successful_runtime_ids": successful_runtime_ids,
            "successful_quota_scope_keys": successful_quota_scope_keys,
            "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
            "runtime_pool_summary": await _runtime_pool_summary(),
            "attempts": attempts,
        },
        cli_evidence,
    )
