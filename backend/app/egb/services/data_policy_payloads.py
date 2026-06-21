"""External payload and safe-summary helpers for EGB data policy."""

import hashlib
import json
import sys
from typing import Any, Callable, Dict, Optional, Set

from backend.app.egb.services.data_policy_models import DataPolicyConfig


SAFE_FIELDS = {
    "evidence_id",
    "run_id",
    "trace_id",
    "span_id",
    "intent_id",
    "decision_id",
    "playbook_id",
    "workspace_id",
    "external_job_id",
    "external_run_id",
    "tool_name",
    "content_hash",
    "output_hash",
    "tool_args_hash",
    "output_fingerprint",
    "key_fields_hash_map",
    "total_tokens",
    "total_cost_usd",
    "total_latency_ms",
    "llm_calls",
    "tool_calls",
    "retrieval_calls",
    "error_count",
    "retry_count",
    "tool_names",
    "source_names",
    "policy_names",
    "status",
    "success",
    "passed",
    "strictness_level",
    "drift_level",
    "stability_score",
    "created_at",
    "updated_at",
    "started_at",
    "ended_at",
    "deep_link_to_external_log",
    "callback_received_at",
}

EXTERNAL_JOB_PAYLOAD_RETENTION_DAYS = 30
EXTERNAL_JOB_PAYLOAD_PII_REDACTION = True
EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB = 1

EXTERNAL_JOB_SENSITIVE_FIELDS = [
    "password",
    "token",
    "api_key",
    "secret",
    "email",
    "phone",
    "ssn",
    "credit_card",
    "authorization",
    "bearer",
    "x-api-key",
]

EXTERNAL_JOB_DEEP_LINK_ONLY_CONDITIONS = [
    "payload_size > 1MB",
    "contains_sensitive_data",
    "external_system_has_audit_log",
]

EXTERNAL_JOB_RAW_PAYLOAD_SAFE_KEYS = {
    "tool_name",
    "status",
    "timestamp",
}


def calculate_payload_size_mb(payload: Dict[str, Any]) -> float:
    """Return the existing payload size approximation in MB."""
    return sys.getsizeof(json.dumps(payload)) / (1024 * 1024)


def fingerprint_payload(payload: Dict[str, Any]) -> str:
    """Return the existing 32-character sha256 payload fingerprint."""
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload_str.encode()).hexdigest()[:32]


def should_store_external_payload_raw(
    *,
    payload_size_mb: float,
    contains_sensitive_data: bool,
    has_deep_link: bool,
    max_size_mb: float = EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB,
) -> bool:
    """Return whether raw external payload content may be stored."""
    if has_deep_link:
        return False
    if payload_size_mb > max_size_mb:
        return False
    if contains_sensitive_data:
        return False
    return True


def build_external_job_payload_summary(
    *,
    payload: Dict[str, Any],
    tool_name: str,
    config: DataPolicyConfig,
    redact_dict: Callable[[Dict[str, Any], Optional[Set[str]]], Dict[str, Any]],
    deep_link: Optional[str] = None,
    contains_sensitive_data: bool = False,
    max_size_mb: float = EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB,
    pii_redaction: bool = EXTERNAL_JOB_PAYLOAD_PII_REDACTION,
) -> Dict[str, Any]:
    """Build the existing external job payload safe summary."""
    payload_size_mb = calculate_payload_size_mb(payload)
    result = {
        "tool_name": tool_name,
        "payload_size_mb": payload_size_mb,
    }

    if deep_link:
        result["deep_link_to_external_log"] = deep_link

    if not should_store_external_payload_raw(
        payload_size_mb=payload_size_mb,
        contains_sensitive_data=contains_sensitive_data,
        has_deep_link=deep_link is not None,
        max_size_mb=max_size_mb,
    ):
        result["store_strategy"] = "deep_link_only"
        return result

    result["output_fingerprint"] = fingerprint_payload(payload)
    result["output_fingerprint_type"] = "sha256"

    if config.store_raw_output:
        if pii_redaction:
            result["redacted_payload"] = redact_dict(
                payload,
                EXTERNAL_JOB_RAW_PAYLOAD_SAFE_KEYS,
            )
        else:
            result["raw_payload"] = payload

    result["store_strategy"] = "fingerprint_with_optional_raw"
    return result
