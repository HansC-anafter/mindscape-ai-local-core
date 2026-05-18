"""
Meeting engine text generation mixin.

Routes all meeting text generation through the bound executor runtime.
"""

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from backend.app.services.external_agents.bridge.codex_cli_runner import (
    DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
    resolve_codex_cli_binary as _resolve_codex_cli_binary,
    resolve_codex_cli_cwd as _resolve_codex_cli_cwd,
    run_codex_cli_subprocess as _run_shared_codex_cli_subprocess,
    sanitize_codex_last_message as _sanitize_direct_codex_last_message,
    should_use_direct_codex_cli_subprocess as _should_use_direct_codex_cli_subprocess,
)
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure as _classify_codex_cli_runtime_failure,
    should_retry_codex_runtime_fault as _should_retry_codex_runtime_fault,
)

logger = logging.getLogger(__name__)


class CodexPoolAdmissionBlockedError(RuntimeError):
    pass


_NON_RETRIABLE_RUNTIME_PATTERNS = (
    "terminalquotaerror",
    "exhausted your capacity",
    "usage limit",
    "quota exceeded",
    "resource_exhausted",
    "resource exhausted",
    "rate limit",
    "too many requests",
    "not supported when using codex",
)

_RETRYABLE_RUNTIME_PATTERNS = (
    "no websocket client connected",
    "websocket client",
    "ws client",
    "not connected",
    "connection closed",
    "temporarily unavailable",
    "unavailable",
    "timed out",
    "timeout",
    "no available codex runtimes in pool",
    "codex pool admission blocked",
    "no_runnable_runtimes",
    "preferred codex runtime unavailable",
)

_CODEX_POOL_RETRYABLE_RUNTIME_PATTERNS = (
    "you've hit your usage limit",
    "usage limit",
    "rate limit",
    "quota exceeded",
    "quota exhausted",
    "insufficient quota",
    "too many requests",
    "resource_exhausted",
    "resource exhausted",
    "deactivated_workspace",
    'code":"deactivated_workspace"',
    "access token could not be refreshed",
    "refresh token was already used",
    "please log out and sign in again",
)

_EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS = (2.0, 4.0, 8.0, 16.0, 30.0)


def _is_non_retriable_runtime_error(exc: Exception) -> bool:
    """Return True when the runtime error should fail fast.

    The Gemini CLI runtime bridge already performs one internal refresh/retry
    for auth/quota faults. If the error still bubbles up here, retrying the
    whole meeting turn just burns additional budget and delays failure.
    """
    text = str(exc or "").lower()
    return any(pattern in text for pattern in _NON_RETRIABLE_RUNTIME_PATTERNS)


def _is_retryable_runtime_error_text(error: Optional[str]) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    if any(pattern in text for pattern in _NON_RETRIABLE_RUNTIME_PATTERNS):
        return False
    return any(pattern in text for pattern in _RETRYABLE_RUNTIME_PATTERNS)


def _is_codex_pool_retryable_runtime_error_text(error: Optional[str]) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    if _is_retryable_runtime_error_text(text):
        return True
    return any(pattern in text for pattern in _CODEX_POOL_RETRYABLE_RUNTIME_PATTERNS)


def _is_runtime_error_retryable_for_executor(
    executor_runtime: Optional[str],
    error: Optional[str],
) -> bool:
    if str(executor_runtime or "").strip().lower() == "codex_cli":
        return _is_codex_pool_retryable_runtime_error_text(error)
    return _is_retryable_runtime_error_text(error)


def _is_runtime_error_non_retriable_for_executor(
    executor_runtime: Optional[str],
    exc: Exception,
) -> bool:
    if isinstance(exc, CodexPoolAdmissionBlockedError):
        return True
    if (
        str(executor_runtime or "").strip().lower() == "codex_cli"
        and _is_codex_pool_retryable_runtime_error_text(str(exc))
    ):
        return False
    return _is_non_retriable_runtime_error(exc)


def _executor_runtime_attempt_count() -> int:
    raw = os.environ.get("MINDSCAPE_MEETING_EXECUTOR_RUNTIME_ATTEMPTS", "").strip()
    if not raw:
        return 6
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _executor_runtime_retry_delay(attempt_index: int) -> float:
    if attempt_index < len(_EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS):
        return _EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS[attempt_index]
    return _EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS[-1]


def _codex_pool_wait_attempt_count() -> int:
    raw = os.environ.get("MINDSCAPE_CODEX_POOL_WAIT_ATTEMPTS", "6").strip()
    try:
        return max(1, min(12, int(raw)))
    except ValueError:
        return 6


def _codex_pool_admission_error_text(admission: Dict[str, Any]) -> str:
    reason = str(admission.get("reason") or "no_runnable_runtimes").strip()
    runnable = admission.get("runnable_runtime_count", 0)
    healthy = admission.get("healthy_runtime_count", 0)
    probation = admission.get("probation_runtime_count", 0)
    quarantined = admission.get("quarantined_runtime_count", 0)
    cooldown = admission.get("cooldown_runtime_count", 0)
    failures = admission.get("failure_counts")
    failure_text = f", failures={failures}" if failures else ""
    return (
        "Codex pool admission blocked: "
        f"{reason} "
        f"(runnable={runnable}, healthy={healthy}, probation={probation}, "
        f"quarantined={quarantined}, cooldown={cooldown}{failure_text})"
    )

from backend.app.services.orchestration.meeting.generation_core.direct_codex_generation_mixin import (
    MeetingGenerationDirectCodexGenerationMixin,
)
from backend.app.services.orchestration.meeting.generation_core.direct_codex_pool_mixin import (
    MeetingGenerationDirectCodexPoolMixin,
)
from backend.app.services.orchestration.meeting.generation_core.events_mixin import (
    MeetingGenerationEventsMixin,
)
from backend.app.services.orchestration.meeting.generation_core.executor_bridge_mixin import (
    MeetingGenerationExecutorBridgeMixin,
)


class MeetingGenerationMixin(
    MeetingGenerationExecutorBridgeMixin,
    MeetingGenerationDirectCodexGenerationMixin,
    MeetingGenerationDirectCodexPoolMixin,
    MeetingGenerationEventsMixin,
):
    """Mixin providing LLM text generation methods for MeetingEngine."""
