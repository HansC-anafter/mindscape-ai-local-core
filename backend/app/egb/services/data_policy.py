"""EGB data policy public facade."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

from backend.app.egb.services.data_policy_models import (
    DataClassification,
    DataPolicyConfig,
    RedactionRule,
    RetentionPolicy,
)
from backend.app.egb.services.data_policy_payloads import (
    EXTERNAL_JOB_DEEP_LINK_ONLY_CONDITIONS,
    EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB,
    EXTERNAL_JOB_PAYLOAD_PII_REDACTION,
    EXTERNAL_JOB_PAYLOAD_RETENTION_DAYS,
    EXTERNAL_JOB_SENSITIVE_FIELDS,
    SAFE_FIELDS,
    build_external_job_payload_summary,
    should_store_external_payload_raw,
)
from backend.app.egb.services.data_policy_redaction import PIIRedactor


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class DataPolicy:
    """
    EGB data retention and redaction policy service.

    The public facade owns singleton access and delegates pure model,
    redaction, and external payload helpers to private seams.
    """

    SAFE_FIELDS = SAFE_FIELDS
    EXTERNAL_JOB_PAYLOAD_RETENTION_DAYS = EXTERNAL_JOB_PAYLOAD_RETENTION_DAYS
    EXTERNAL_JOB_PAYLOAD_PII_REDACTION = EXTERNAL_JOB_PAYLOAD_PII_REDACTION
    EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB = EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB
    EXTERNAL_JOB_SENSITIVE_FIELDS = EXTERNAL_JOB_SENSITIVE_FIELDS
    EXTERNAL_JOB_DEEP_LINK_ONLY_CONDITIONS = EXTERNAL_JOB_DEEP_LINK_ONLY_CONDITIONS

    def __init__(self, config: Optional[DataPolicyConfig] = None):
        """Initialize the data policy with the existing defaults."""
        self.config = config or DataPolicyConfig()
        self.redactor = PIIRedactor(config)

    def redact(self, text: str) -> str:
        """Redact PII or sensitive text according to the configured rules."""
        return self.redactor.redact(text)

    def redact_dict(
        self,
        data: Dict[str, Any],
        safe_keys: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Redact dictionary values except explicitly safe keys."""
        return self.redactor.redact_dict(data, safe_keys)

    def create_safe_summary(
        self,
        raw_data: Dict[str, Any],
        include_llm_explanation: bool = False,
    ) -> Dict[str, Any]:
        """
        Build the EGB safe summary that may be stored.

        Only fields in SAFE_FIELDS are retained. Optional LLM explanations are
        retained only when enabled and redacted before returning.
        """
        summary = {}

        for key, value in raw_data.items():
            if key in self.SAFE_FIELDS:
                summary[key] = value
            elif key == "llm_explanation" and include_llm_explanation:
                if self.config.store_llm_explanations and value:
                    summary[key] = self.redact(value)

        return summary

    def should_store_in_egb(self, field_name: str) -> bool:
        """Return whether a field is allowed in the EGB safe summary."""
        return field_name in self.SAFE_FIELDS

    def get_retention_days(self, policy: RetentionPolicy) -> Optional[int]:
        """Return the configured number of retention days for a policy."""
        if policy == RetentionPolicy.PERMANENT:
            return None
        if policy == RetentionPolicy.LONG_TERM:
            return 90
        if policy == RetentionPolicy.SHORT_TERM:
            return 7
        if policy == RetentionPolicy.EPHEMERAL:
            return 1
        if policy == RetentionPolicy.NO_STORE:
            return 0
        return None

    def get_expiry_date(self, policy: RetentionPolicy) -> Optional[datetime]:
        """Return the UTC expiry datetime for a retention policy."""
        days = self.get_retention_days(policy)
        if days is None:
            return None
        if days == 0:
            return _utc_now()
        return _utc_now() + timedelta(days=days)

    def process_external_job_payload(
        self,
        payload: Dict[str, Any],
        tool_name: str,
        deep_link: Optional[str] = None,
        contains_sensitive_data: bool = False,
    ) -> Dict[str, Any]:
        """Build the safe external job payload summary."""
        return build_external_job_payload_summary(
            payload=payload,
            tool_name=tool_name,
            config=self.config,
            redact_dict=self.redact_dict,
            deep_link=deep_link,
            contains_sensitive_data=contains_sensitive_data,
            max_size_mb=self.EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB,
            pii_redaction=self.EXTERNAL_JOB_PAYLOAD_PII_REDACTION,
        )

    def should_store_external_payload_raw(
        self, payload_size_mb: float, contains_sensitive_data: bool, has_deep_link: bool
    ) -> bool:
        """Return whether an external payload may be stored as raw content."""
        return should_store_external_payload_raw(
            payload_size_mb=payload_size_mb,
            contains_sensitive_data=contains_sensitive_data,
            has_deep_link=has_deep_link,
            max_size_mb=self.EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB,
        )


_global_policy: Optional[DataPolicy] = None


def get_data_policy() -> DataPolicy:
    """Return the process-level global DataPolicy instance."""
    global _global_policy
    if _global_policy is None:
        _global_policy = DataPolicy()
    return _global_policy


__all__ = [
    "DataClassification",
    "DataPolicy",
    "DataPolicyConfig",
    "PIIRedactor",
    "RedactionRule",
    "RetentionPolicy",
    "get_data_policy",
]
