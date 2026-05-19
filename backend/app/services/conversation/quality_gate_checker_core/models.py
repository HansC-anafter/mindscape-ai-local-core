"""Models for quality gate checks."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class QualityGateResult:
    """Result of a quality gate check."""

    passed: bool
    failed_gates: List[str] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.failed_gates is None:
            self.failed_gates = []
        if self.details is None:
            self.details = {}
