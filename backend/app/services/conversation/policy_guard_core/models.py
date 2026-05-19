"""Models for policy checks."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PolicyCheckResult:
    """Result of a policy check."""

    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    proposed_action: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
