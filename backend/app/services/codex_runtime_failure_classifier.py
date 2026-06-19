"""Shared Codex runtime failure classification.

This module owns the runtime fault semantics used by meeting, task execution,
core_llm, and E2E preflight. Callers may decide how to report a classified
fault, but they must not maintain separate quota/auth/version classifiers.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def looks_like_codex_quota_exhaustion(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    quota_text = any(
        marker in normalized
        for marker in (
            "usage limit",
            "rate limit",
            "quota exceeded",
            "quota exhausted",
            "insufficient quota",
            "too many requests",
            "resource_exhausted",
            "resource exhausted",
        )
    )
    if quota_text:
        return True
    return bool(
        re.search(
            r"(?:unexpected status|status|http|error|code|last_error_code)\D{0,20}429\b",
            normalized,
        )
    )


def looks_like_codex_version_incompatible(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    return (
        "requires a newer version of codex" in normalized
        or "please upgrade to the latest app or cli" in normalized
    )


def looks_like_codex_auth_failure(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    markers = (
        "401 unauthorized",
        "unauthorized",
        "missing bearer",
        "missing bearer or basic authentication",
        "authentication failed",
        "invalid api key",
        "incorrect api key",
        "missing api key",
        "deactivated_workspace",
        'code":"deactivated_workspace"',
        "access token could not be refreshed",
        "refresh token was already used",
        "refresh token was rejected",
        "stale_refresh_token",
        "invalid_grant",
        "invalid grant",
        "token_refresh_http_400",
        "token_refresh_http_401",
        "token_refresh_http_403",
        "missing_refresh_token",
        "please log out and sign in again",
    )
    return any(marker in normalized for marker in markers) and not looks_like_codex_quota_exhaustion(
        normalized
    )


def classify_codex_cli_runtime_failure(message: str) -> dict[str, str]:
    normalized = str(message or "")
    if looks_like_codex_auth_failure(normalized):
        lowered = normalized.lower()
        if "deactivated_workspace" in lowered:
            return {"fault_kind": "auth", "error_code": "deactivated_workspace"}
        if "refresh token was already used" in lowered:
            return {"fault_kind": "auth", "error_code": "stale_refresh_token"}
        if (
            "stale_refresh_token" in lowered
            or "invalid_grant" in lowered
            or "token_refresh_http_400" in lowered
            or "token_refresh_http_401" in lowered
            or "token_refresh_http_403" in lowered
        ):
            return {"fault_kind": "auth", "error_code": "stale_refresh_token"}
        if "missing_refresh_token" in lowered:
            return {"fault_kind": "auth", "error_code": "missing_refresh_token"}
        return {"fault_kind": "auth", "error_code": "auth_failure"}
    if looks_like_codex_quota_exhaustion(normalized):
        return {"fault_kind": "quota", "error_code": "429"}
    if looks_like_codex_version_incompatible(normalized):
        return {
            "fault_kind": "runtime",
            "error_code": "codex_cli_version_incompatible",
        }
    lowered = normalized.lower()
    if "subprocess stalled after" in lowered:
        return {"fault_kind": "runtime", "error_code": "timeout"}
    if "no activity for" in lowered:
        return {"fault_kind": "runtime", "error_code": "timeout"}
    if "probe_transport_error" in lowered:
        return {"fault_kind": "runtime", "error_code": "probe_transport_error"}
    if "attempted to create a null object" in lowered:
        return {"fault_kind": "runtime", "error_code": "codex_cli_panic"}
    if "unknown variant" in lowered and "model_reasoning_effort" in lowered:
        return {"fault_kind": "runtime", "error_code": "codex_cli_config_invalid"}
    if "no such file or directory (os error 2)" in lowered:
        return {"fault_kind": "runtime", "error_code": "runtime_not_found"}
    return {"fault_kind": "runtime", "error_code": "runtime_error"}


def should_retry_codex_runtime_fault(message: str) -> bool:
    classification = classify_codex_cli_runtime_failure(message)
    fault_kind = str(classification.get("fault_kind") or "").strip()
    error_code = str(classification.get("error_code") or "").strip()
    if fault_kind in {"quota", "auth"}:
        return True
    return error_code in {"timeout", "runtime_not_found"}


def extract_codex_quota_reset_at(message: str) -> Optional[datetime]:
    normalized = str(message or "")
    if not normalized:
        return None
    match = re.search(
        r"try again at\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        candidate = re.sub(
            r"(\d{1,2})(st|nd|rd|th)",
            r"\1",
            match.group(1),
            flags=re.IGNORECASE,
        ).replace(",", "")
        for fmt in ("%B %d %Y %I:%M %p", "%b %d %Y %I:%M %p"):
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    time_match = re.search(
        r"try again at\s+(\d{1,2}:\d{2}\s+[AP]M)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if time_match:
        try:
            parsed_time = datetime.strptime(time_match.group(1), "%I:%M %p").time()
            now = datetime.now(timezone.utc)
            candidate = datetime.combine(now.date(), parsed_time, tzinfo=timezone.utc)
            if candidate <= now:
                candidate = candidate + timedelta(days=1)
            return candidate
        except ValueError:
            return None
    return None
