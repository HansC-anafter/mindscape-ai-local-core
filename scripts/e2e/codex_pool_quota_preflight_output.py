"""CLI argument and compact output helpers for Codex quota preflight."""

from __future__ import annotations

import argparse
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Codex pool quota before running expensive E2E work.",
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--max-runtime-probes", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--stall-timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--required-login-email",
        default="",
        help="Require the selected Codex runtime to expose this login email.",
    )
    parser.add_argument(
        "--exclude-runtime-id",
        action="append",
        default=[],
        help="Exclude a runtime before the first probe; repeat to simulate prior pool failures.",
    )
    parser.add_argument(
        "--target-successes",
        type=int,
        default=1,
        help="Require this many successful Codex CLI quota probes before returning available.",
    )
    parser.add_argument(
        "--continue-after-success",
        action="store_true",
        help="Continue probing until max-runtime-probes even after target-successes is reached.",
    )
    parser.add_argument(
        "--audit-all-account-homes",
        action="store_true",
        help=(
            "Probe every pool-enabled account-home runtime directly, ignoring DB cooldown "
            "and resolver admission. Use for external true/false audits, not normal scheduling."
        ),
    )
    parser.add_argument(
        "--compact-output",
        action="store_true",
        help="Print only per-attempt probe evidence and aggregate counts.",
    )
    return parser.parse_args()


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    attempts = result.get("attempts")
    if not isinstance(attempts, list):
        attempts = []

    compact_attempts: list[dict[str, Any]] = []
    failure_counts: dict[str, int] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        identity = attempt.get("runtime_account_identity")
        if not isinstance(identity, dict):
            identity = {}
        probe = attempt.get("probe")
        if not isinstance(probe, dict):
            probe = {}
        error_code = str(attempt.get("error_code") or "").strip()
        fault_kind = str(attempt.get("fault_kind") or "").strip()
        status = str(attempt.get("status") or "").strip()
        if error_code:
            failure_counts[error_code] = failure_counts.get(error_code, 0) + 1
        compact_attempts.append(
            {
                "attempt": attempt.get("attempt"),
                "status": status,
                "runtime_id": attempt.get("selected_runtime_id"),
                "login_email": identity.get("login_email"),
                "account_key": identity.get("account_key"),
                "quota_scope_key": attempt.get("quota_scope_key"),
                "counted_quota_scope_key": attempt.get("counted_quota_scope_key"),
                "db_cooldown_until": attempt.get("db_cooldown_until"),
                "db_last_error_code": attempt.get("db_last_error_code"),
                "db_probe_state": attempt.get("db_probe_state"),
                "db_last_probe_error_code": attempt.get("db_last_probe_error_code"),
                "db_last_probe_success_at": attempt.get("db_last_probe_success_at"),
                "auth_mtime_ns": attempt.get("auth_mtime_ns"),
                "fault_kind": fault_kind or None,
                "error_code": error_code or None,
                "probe_success": probe.get("success"),
                "probe_returncode": probe.get("returncode"),
                "probe_error": str(probe.get("error") or "")[:300] or None,
                "probe_output": str(probe.get("output") or "")[:200] or None,
            }
        )

    pool_summary = result.get("runtime_pool_summary")
    if not isinstance(pool_summary, dict):
        pool_summary = {}

    return {
        "status": result.get("status"),
        "workspace_id": result.get("workspace_id"),
        "target_successes": result.get("target_successes"),
        "successful_runtime_count": result.get("successful_runtime_count"),
        "successful_quota_scope_count": result.get("successful_quota_scope_count"),
        "successful_runtime_ids": result.get("successful_runtime_ids"),
        "successful_quota_scope_keys": result.get("successful_quota_scope_keys"),
        "codex_cli_binary": result.get("codex_cli_binary"),
        "codex_cli_version": result.get("codex_cli_version"),
        "minimum_supported_codex_cli_version": result.get(
            "minimum_supported_codex_cli_version"
        ),
        "required_flags_supported": result.get("required_flags_supported"),
        "codex_cli_compatible": result.get("codex_cli_compatible"),
        "attempt_count": len(compact_attempts),
        "failure_counts": failure_counts,
        "pool_summary": {
            "pool_enabled_runtime_count": pool_summary.get("pool_enabled_runtime_count"),
            "runnable_runtime_count": pool_summary.get("runnable_runtime_count"),
            "probe_available_runtime_count": pool_summary.get(
                "probe_available_runtime_count"
            ),
            "active_cooldown_count": pool_summary.get("active_cooldown_count"),
            "probe_state_counts": pool_summary.get("probe_state_counts"),
            "failure_counts": pool_summary.get("failure_counts"),
            "next_cooldown_until": pool_summary.get("next_cooldown_until"),
        },
        "audit_mode": result.get("audit_mode"),
        "audited_runtime_count": result.get("audited_runtime_count"),
        "attempts": compact_attempts,
    }
