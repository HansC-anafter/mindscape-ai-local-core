"""Public data policy models used by the EGB data policy facade."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class DataClassification(str, Enum):
    """Data classification labels for redaction and retention decisions."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    PII = "pii"


class RetentionPolicy(str, Enum):
    """Retention policy labels used by DataPolicy."""

    PERMANENT = "permanent"
    LONG_TERM = "long_term"
    SHORT_TERM = "short_term"
    EPHEMERAL = "ephemeral"
    NO_STORE = "no_store"


@dataclass
class RedactionRule:
    """One regex-based redaction rule."""

    name: str
    pattern: str
    replacement: str = "[REDACTED]"
    classification: DataClassification = DataClassification.PII


@dataclass
class DataPolicyConfig:
    """Configuration for retention and redaction behavior."""

    raw_trace_retention: RetentionPolicy = RetentionPolicy.LONG_TERM
    evidence_retention: RetentionPolicy = RetentionPolicy.PERMANENT
    llm_explanation_retention: RetentionPolicy = RetentionPolicy.LONG_TERM

    store_raw_output: bool = False
    store_raw_input: bool = False
    store_llm_explanations: bool = True

    redact_emails: bool = True
    redact_phones: bool = True
    redact_tokens: bool = True
    redact_urls: bool = False
    redact_ips: bool = True
    redact_credit_cards: bool = True

    custom_rules: List[RedactionRule] = field(default_factory=list)
