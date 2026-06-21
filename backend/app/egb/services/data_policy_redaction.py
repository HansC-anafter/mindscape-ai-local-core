"""PII redaction helpers for EGB data policy."""

import logging
import re
from typing import Any, Dict, List, Optional, Set

from backend.app.egb.services.data_policy_models import (
    DataClassification,
    DataPolicyConfig,
    RedactionRule,
)

logger = logging.getLogger(__name__)


DEFAULT_RULES = [
    RedactionRule(
        name="email",
        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        replacement="[EMAIL]",
        classification=DataClassification.PII,
    ),
    RedactionRule(
        name="phone",
        pattern=r"\b(?:\+?1[-.\s]?)?(?:\([0-9]{3}\)|[0-9]{3})[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
        replacement="[PHONE]",
        classification=DataClassification.PII,
    ),
    RedactionRule(
        name="taiwan_phone",
        pattern=r"\b09[0-9]{8}\b",
        replacement="[PHONE]",
        classification=DataClassification.PII,
    ),
    RedactionRule(
        name="ip_address",
        pattern=r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
        replacement="[IP]",
        classification=DataClassification.SENSITIVE,
    ),
    RedactionRule(
        name="credit_card",
        pattern=r"\b(?:[0-9]{4}[-\s]?){3}[0-9]{4}\b",
        replacement="[CARD]",
        classification=DataClassification.PII,
    ),
    RedactionRule(
        name="api_key",
        pattern=r"\b(sk-|pk-|api[-_]?key[-_]?)[A-Za-z0-9]{20,}\b",
        replacement="[API_KEY]",
        classification=DataClassification.SENSITIVE,
    ),
    RedactionRule(
        name="jwt_token",
        pattern=r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        replacement="[JWT]",
        classification=DataClassification.SENSITIVE,
    ),
    RedactionRule(
        name="bearer_token",
        pattern=r"\bBearer\s+[A-Za-z0-9_-]+\b",
        replacement="Bearer [TOKEN]",
        classification=DataClassification.SENSITIVE,
    ),
]


class PIIRedactor:
    """Redact PII or sensitive fields before data policy storage."""

    DEFAULT_RULES = DEFAULT_RULES

    def __init__(self, config: Optional[DataPolicyConfig] = None):
        """Initialize the redactor with the existing default rules."""
        self.config = config or DataPolicyConfig()
        self._rules = self._build_rules()
        self._compiled_patterns: Dict[str, re.Pattern] = {}
        self._compile_patterns()

    def _build_rules(self) -> List[RedactionRule]:
        """Build the enabled rule list from configuration toggles."""
        rules = []

        for rule in self.DEFAULT_RULES:
            if rule.name == "email" and self.config.redact_emails:
                rules.append(rule)
            elif rule.name in ["phone", "taiwan_phone"] and self.config.redact_phones:
                rules.append(rule)
            elif rule.name == "ip_address" and self.config.redact_ips:
                rules.append(rule)
            elif rule.name == "credit_card" and self.config.redact_credit_cards:
                rules.append(rule)
            elif (
                rule.name in ["api_key", "jwt_token", "bearer_token"]
                and self.config.redact_tokens
            ):
                rules.append(rule)

        rules.extend(self.config.custom_rules)
        return rules

    def _compile_patterns(self) -> None:
        """Compile enabled regex patterns and keep invalid-rule warnings."""
        for rule in self._rules:
            try:
                self._compiled_patterns[rule.name] = re.compile(
                    rule.pattern, re.IGNORECASE
                )
            except re.error as e:
                logger.warning(
                    f"DataPolicy: Invalid regex pattern for {rule.name}: {e}"
                )

    def redact(self, text: str) -> str:
        """Redact a text value with all enabled rules."""
        if not text:
            return text

        result = text
        for rule in self._rules:
            pattern = self._compiled_patterns.get(rule.name)
            if pattern:
                result = pattern.sub(rule.replacement, result)

        return result

    def redact_dict(
        self,
        data: Dict[str, Any],
        safe_keys: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Redact dictionary string values except explicitly safe keys."""
        safe_keys = safe_keys or set()
        result = {}

        for key, value in data.items():
            if key in safe_keys:
                result[key] = value
            elif isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value, safe_keys)
            elif isinstance(value, list):
                result[key] = [
                    self.redact(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value

        return result
