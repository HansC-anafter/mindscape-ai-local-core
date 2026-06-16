from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class HealthIssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HealthIssue:
    def __init__(
        self,
        issue_type: str,
        severity: HealthIssueSeverity,
        message: str,
        action_url: Optional[str] = None,
        tool_type: Optional[str] = None
    ):
        self.type = issue_type
        self.severity = severity
        self.message = message
        self.action_url = action_url
        self.tool_type = tool_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity.value,
            "message": self.message,
            "action_url": self.action_url,
            "tool_type": self.tool_type
        }
