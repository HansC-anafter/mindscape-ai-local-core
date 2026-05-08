"""Background quota discovery for materialized Codex account-home runtimes."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from backend.app.services.codex_pool_health import (
    coerce_datetime,
    is_executable_runtime_metadata,
    read_health_metadata,
    stamp_runtime_failure,
    stamp_runtime_probe_failure,
    stamp_runtime_probe_success,
    stamp_runtime_success,
)
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
    extract_codex_quota_reset_at,
)


_SUPPORTED_AUTH_TYPES = frozenset({"host_session", "none"})
_AUTH_FAILURE_COOLDOWN_SECONDS = 1800
_QUOTA_COOLDOWN_SECONDS = 300


@dataclass(frozen=True)
class CodexPoolQuotaDiscoverySummary:
    scanned_runtime_count: int
    available_runtime_count: int
    failed_runtime_count: int
    updated_runtime_ids: tuple[str, ...]
    attempts: tuple[dict[str, Any], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "scanned_runtime_count": self.scanned_runtime_count,
            "available_runtime_count": self.available_runtime_count,
            "failed_runtime_count": self.failed_runtime_count,
            "updated_runtime_ids": list(self.updated_runtime_ids),
            "attempts": list(self.attempts),
        }


ProbeRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class CodexPoolQuotaDiscoveryService:
    """Probe account-home candidates without using the selection path."""

    def __init__(
        self,
        *,
        runtime_loader: Optional[Callable[[], list[Any]]] = None,
        runtime_commit: Optional[Callable[[list[Any]], None]] = None,
        probe_runner: Optional[ProbeRunner] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._runtime_commit = runtime_commit
        self._probe_runner = probe_runner or self._run_real_codex_probe
        self._loaded_db: Any = None

    async def discover(
        self,
        *,
        limit: Optional[int] = None,
        timeout_seconds: float = 90.0,
        stall_timeout_seconds: float = 30.0,
    ) -> CodexPoolQuotaDiscoverySummary:
        runtimes = self._load_candidates()
        if limit is not None and limit >= 0:
            runtimes = runtimes[:limit]

        attempts: list[dict[str, Any]] = []
        updated_runtimes: list[Any] = []
        updated_runtime_ids: list[str] = []
        available_count = 0
        failed_count = 0
        now = datetime.now(timezone.utc)
        for runtime in runtimes:
            runtime_id = str(getattr(runtime, "id", "") or "").strip()
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            bundle = {
                "env": self._host_session_env_from_metadata(metadata),
                "selected_runtime_id": runtime_id,
                "quota_scope_key": self._quota_scope_key(metadata, runtime_id=runtime_id),
                "runtime_account_identity": self._runtime_identity(metadata),
            }
            probe = await self._probe_runner(
                {
                    "bundle": bundle,
                    "timeout_seconds": timeout_seconds,
                    "stall_timeout_seconds": stall_timeout_seconds,
                }
            )
            success = bool(probe.get("success"))
            returncode = probe.get("returncode")
            attempt = {
                "selected_runtime_id": runtime_id,
                "login_email": bundle["runtime_account_identity"].get("login_email"),
                "quota_scope_key": bundle.get("quota_scope_key"),
                "probe": probe,
            }
            if success:
                runtime.cooldown_until = None
                runtime.last_error_code = None
                updated = stamp_runtime_success(
                    metadata,
                    auth_type=str(getattr(runtime, "auth_type", "") or ""),
                    now=now,
                )
                runtime.extra_metadata = stamp_runtime_probe_success(
                    updated,
                    returncode=int(returncode or 0),
                    source_event_id=f"quota-discovery:{uuid.uuid4()}",
                    now=now,
                )
                attempt["status"] = "available"
                available_count += 1
            else:
                error_text = str(probe.get("error") or probe.get("output") or "").strip()
                classification = classify_codex_cli_runtime_failure(error_text)
                fault_kind = str(classification.get("fault_kind") or "runtime").strip()
                error_code = str(
                    classification.get("error_code") or "runtime_error"
                ).strip()
                runtime.last_error_code = error_code
                if fault_kind == "quota":
                    reset_at = coerce_datetime(extract_codex_quota_reset_at(error_text))
                    cooldown_until = now + timedelta(seconds=_QUOTA_COOLDOWN_SECONDS)
                    if reset_at and reset_at > cooldown_until:
                        cooldown_until = reset_at
                    runtime.cooldown_until = cooldown_until
                elif fault_kind == "auth":
                    runtime.cooldown_until = now + timedelta(
                        seconds=_AUTH_FAILURE_COOLDOWN_SECONDS
                    )
                updated = stamp_runtime_failure(
                    metadata,
                    error_code=error_code,
                    auth_type=str(getattr(runtime, "auth_type", "") or ""),
                    failure_scope_key=(
                        f"quota:{bundle.get('quota_scope_key')}"
                        if fault_kind == "quota" and bundle.get("quota_scope_key")
                        else f"runtime:{runtime_id}"
                    ),
                    now=now,
                )
                runtime.extra_metadata = stamp_runtime_probe_failure(
                    updated,
                    error_code=error_code,
                    returncode=int(returncode) if returncode is not None else None,
                    source_event_id=f"quota-discovery:{uuid.uuid4()}",
                    now=now,
                )
                attempt.update(
                    {
                        "status": "failed",
                        "fault_kind": fault_kind,
                        "error_code": error_code,
                    }
                )
                failed_count += 1
            attempts.append(attempt)
            updated_runtimes.append(runtime)
            updated_runtime_ids.append(runtime_id)

        if updated_runtimes:
            self._commit(updated_runtimes)
        elif self._loaded_db is not None:
            self._loaded_db.close()
            self._loaded_db = None

        return CodexPoolQuotaDiscoverySummary(
            scanned_runtime_count=len(runtimes),
            available_runtime_count=available_count,
            failed_runtime_count=failed_count,
            updated_runtime_ids=tuple(updated_runtime_ids),
            attempts=tuple(attempts),
        )

    def _load_candidates(self) -> list[Any]:
        runtimes = (
            list(self._runtime_loader())
            if self._runtime_loader is not None
            else self._load_database_runtimes()
        )
        now = datetime.now(timezone.utc)
        candidates: list[Any] = []
        for runtime in runtimes:
            auth_type = str(getattr(runtime, "auth_type", "") or "").strip().lower()
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(metadata, auth_type=auth_type)
            cooldown_until = coerce_datetime(getattr(runtime, "cooldown_until", None))
            if auth_type not in _SUPPORTED_AUTH_TYPES:
                continue
            if cooldown_until and cooldown_until > now:
                continue
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            if str(health.get("health_state") or "").strip().lower() == "quarantined":
                continue
            if not is_executable_runtime_metadata(metadata, auth_type=auth_type):
                continue
            candidates.append(runtime)
        return candidates

    async def _run_real_codex_probe(self, probe_input: dict[str, Any]) -> dict[str, Any]:
        from backend.app.services.external_agents.bridge.codex_cli_runner import (
            resolve_codex_cli_binary,
            resolve_codex_cli_cwd,
            run_codex_cli_subprocess,
        )
        from backend.app.services.llm.core_llm import _merge_codex_env
        from backend.app.shared.llm_utils import extract_json_from_text

        bundle = dict(probe_input.get("bundle") or {})
        binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
        cwd = resolve_codex_cli_cwd(os.environ.get("HOST_PROJECT_PATH", "").strip())
        with tempfile.NamedTemporaryFile(
            prefix="codex_pool_quota_discovery_",
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
                execution_id=f"codex-pool-quota-discovery-{uuid.uuid4()}",
                timeout=float(probe_input.get("timeout_seconds") or 90.0),
                stall_timeout=float(probe_input.get("stall_timeout_seconds") or 30.0),
            )
        except asyncio.TimeoutError as exc:
            return {
                "success": False,
                "error": str(exc).strip() or "codex_cli quota discovery timed out",
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

    def _load_database_runtimes(self) -> list[Any]:
        from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        self._loaded_db = db
        return (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
                RuntimeEnvironment.auth_type.in_(tuple(_SUPPORTED_AUTH_TYPES)),
            )
            .all()
        )

    def _commit(self, runtimes: list[Any]) -> None:
        if self._runtime_commit is not None:
            self._runtime_commit(runtimes)
            return
        if self._loaded_db is not None:
            try:
                self._loaded_db.commit()
            finally:
                self._loaded_db.close()
                self._loaded_db = None

    @staticmethod
    def _host_session_env_from_metadata(metadata: dict[str, Any]) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("CODEX_HOME", "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            value = str(metadata.get(key) or "").strip()
            if value:
                env[key] = value
        return env

    @staticmethod
    def _quota_scope_key(metadata: dict[str, Any], *, runtime_id: str) -> str:
        account_key = str(metadata.get("account_key") or "").strip()
        if account_key:
            return f"account:{account_key}"
        return str(metadata.get("quota_scope_key") or "").strip() or f"runtime:{runtime_id}"

    @staticmethod
    def _runtime_identity(metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "login_email": str(metadata.get("login_email") or "").strip().lower() or None,
            "account_key": str(metadata.get("account_key") or "").strip() or None,
        }
