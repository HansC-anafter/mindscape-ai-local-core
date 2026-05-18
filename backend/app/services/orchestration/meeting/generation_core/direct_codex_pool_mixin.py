"""Direct Codex pool resolution and subprocess helpers."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting import _generation as generation_module

logger = logging.getLogger(__name__)


class MeetingGenerationDirectCodexPoolMixin:
    async def _fetch_direct_codex_auth_bundle(
        self,
        *,
        excluded_runtime_ids: Optional[set[str]] = None,
        excluded_quota_scope_keys: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        try:
            from backend.app.services.codex_pool_runtime_router import (
                resolve_codex_pool_runtime_bundle,
            )
            from backend.app.services.executor_binding_service import (
                ExecutorBindingService,
            )

            binding_service = ExecutorBindingService()
            workspace_id = str(getattr(getattr(self, "workspace", None), "id", "") or "")
            lease_owner_type, lease_owner_id = self._direct_codex_lease_identity()
            normalized_excluded_runtime_ids = {
                str(runtime_id).strip()
                for runtime_id in (excluded_runtime_ids or set())
                if str(runtime_id).strip()
            }
            normalized_excluded_quota_scope_keys = {
                str(scope_key).strip()
                for scope_key in (excluded_quota_scope_keys or set())
                if str(scope_key).strip()
            }
            cached_bundle = getattr(self, "_bound_direct_codex_auth_bundle", None)
            if isinstance(cached_bundle, dict) and cached_bundle.get("selected_runtime_id"):
                cached_runtime_id = str(
                    cached_bundle.get("selected_runtime_id") or ""
                ).strip()
                cached_quota_scope_key = str(
                    cached_bundle.get("quota_scope_key") or ""
                ).strip()
                cached_probe_state = str(
                    cached_bundle.get("probe_state") or ""
                ).strip().lower()
                cached_probe_success_at = str(
                    cached_bundle.get("last_probe_success_at") or ""
                ).strip()
                if (
                    cached_runtime_id in normalized_excluded_runtime_ids
                    or (
                        cached_quota_scope_key
                        and cached_quota_scope_key in normalized_excluded_quota_scope_keys
                    )
                    or cached_probe_state != "available"
                    or not cached_probe_success_at
                ):
                    self._bound_direct_codex_auth_bundle = None
                elif not (workspace_id and lease_owner_type and lease_owner_id):
                    return dict(cached_bundle)
                else:
                    binding_snapshot = await generation_module.asyncio.to_thread(
                        binding_service.load_binding_snapshot,
                        workspace_id=workspace_id,
                        surface="codex_cli",
                    )
                    if self._binding_snapshot_matches_direct_codex_lease(
                        binding_snapshot,
                        lease_owner_type=lease_owner_type,
                        lease_owner_id=lease_owner_id,
                        runtime_id=cached_runtime_id,
                    ):
                        return dict(cached_bundle)
                    self._bound_direct_codex_auth_bundle = None

            pool_result = await resolve_codex_pool_runtime_bundle(
                workspace_id=workspace_id,
                lease_owner_type=lease_owner_type,
                lease_owner_id=lease_owner_id,
                excluded_runtime_ids=normalized_excluded_runtime_ids,
                excluded_quota_scope_keys=normalized_excluded_quota_scope_keys,
                require_probe_available=True,
                fail_closed_session_lease=False,
                record_runtime_lease=True,
            )
            if (
                str(getattr(self, "executor_runtime", "") or "").strip().lower()
                == "codex_cli"
            ):
                selected_runtime_id = str(
                    pool_result.get("selected_runtime_id") or ""
                ).strip()
                if not selected_runtime_id:
                    reason = str(
                        pool_result.get("error")
                        or "Codex workspace route did not resolve a concrete pool runtime"
                    ).strip()
                    if isinstance(pool_result, dict):
                        result = dict(pool_result)
                        result["error"] = reason
                        return result
                    return {"error": reason}
                selected_quota_scope_key = str(
                    pool_result.get("quota_scope_key") or ""
                ).strip()
                if selected_runtime_id in normalized_excluded_runtime_ids:
                    result = dict(pool_result)
                    result["error"] = (
                        "pool_reused_excluded_runtime: Codex pool resolver returned "
                        f"excluded runtime {selected_runtime_id}"
                    )
                    return result
                if (
                    selected_quota_scope_key
                    and selected_quota_scope_key in normalized_excluded_quota_scope_keys
                ):
                    result = dict(pool_result)
                    result["error"] = (
                        "pool_reused_excluded_quota_scope: Codex pool resolver returned "
                        f"excluded quota scope {selected_quota_scope_key}"
                    )
                    return result
                probe_state = str(pool_result.get("probe_state") or "").strip().lower()
                last_probe_success_at = str(
                    pool_result.get("last_probe_success_at") or ""
                ).strip()
                if probe_state != "available" or not last_probe_success_at:
                    result = dict(pool_result)
                    result["error"] = (
                        "Codex pool admission blocked: probe_state_unavailable "
                        f"(runtime={selected_runtime_id}, probe_state={probe_state or 'missing'})"
                    )
                    return result
                self._bound_direct_codex_auth_bundle = dict(pool_result)
            return pool_result
        except Exception:
            logger.exception("Meeting direct Codex pool lookup failed")
            return {
                "error": "Meeting codex route resolution failed before a runtime could be bound"
            }

    async def _report_direct_codex_runtime_quota_exhausted(
        self,
        runtime_id: str,
        *,
        workspace_id: str = "",
        error_text: str = "",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_fault,
            )

            await report_codex_pool_runtime_fault(
                runtime_id=runtime_id,
                fault_kind="quota",
                workspace_id=workspace_id,
                error_code="429",
                error_text=error_text,
            )
        except Exception:
            logger.exception(
                "Failed to report direct codex quota exhaustion for runtime %s",
                runtime_id,
            )

    async def _report_direct_codex_runtime_auth_failure(
        self,
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_fault,
            )

            await report_codex_pool_runtime_fault(
                runtime_id=runtime_id,
                fault_kind="auth",
                workspace_id=workspace_id,
                error_code=error_code,
            )
        except Exception:
            logger.exception(
                "Failed to report direct codex auth failure for runtime %s",
                runtime_id,
            )

    async def _report_direct_codex_runtime_success(
        self,
        runtime_id: str,
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_success,
            )

            await report_codex_pool_runtime_success(runtime_id=runtime_id)
        except Exception:
            logger.exception(
                "Failed to report direct codex success for runtime %s",
                runtime_id,
            )

    @staticmethod
    def _extract_direct_codex_auth_error_code(error_text: str) -> str:
        normalized = str(error_text or "").strip().lower()
        if "deactivated_workspace" in normalized:
            return "deactivated_workspace"
        if "refresh token was already used" in normalized:
            return "stale_refresh_token"
        if "403" in normalized:
            return "403"
        return "401"

    async def _run_direct_codex_cli_subprocess(
        self,
        *,
        cmd: List[str],
        cwd: str,
        last_message_path: str,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> tuple[int, str, str, str, str]:
        env = generation_module.os.environ.copy()
        if extra_env:
            env.update(
                {
                    str(key): str(value)
                    for key, value in extra_env.items()
                    if value is not None and str(value) != ""
                }
            )

        stall_timeout_raw = generation_module.os.environ.get(
            "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
            str(generation_module.DEFAULT_CLI_STALL_TIMEOUT_SECONDS),
        ).strip()
        try:
            stall_timeout = max(5.0, float(stall_timeout_raw))
        except ValueError:
            stall_timeout = generation_module.DEFAULT_CLI_STALL_TIMEOUT_SECONDS

        try:
            result = await generation_module._run_shared_codex_cli_subprocess(
                cmd=cmd,
                cwd=cwd,
                env=env,
                last_message_path=last_message_path,
                execution_id=str(getattr(self.session, "id", "meeting-direct-codex")),
                timeout=300.0,
                stall_timeout=min(300.0, stall_timeout),
            )
        except generation_module.asyncio.TimeoutError as exc:
            error_text = str(exc).strip() or "codex_cli subprocess stalled without output"
            return (1, "", "", "", error_text)
        return (
            result.returncode,
            result.stdout_text,
            result.stderr_text,
            result.output_text,
            result.synthesized_error or result.combined_output,
        )
