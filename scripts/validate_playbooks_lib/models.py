from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    """Result of a single validation check."""

    check_name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookValidation:
    """Complete validation result for a playbook."""

    playbook_code: str
    capability: str
    results: List[ValidationResult] = field(default_factory=list)
    execution_result: Optional[Dict[str, Any]] = None

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def critical_failures(self) -> List[ValidationResult]:
        return [
            r
            for r in self.results
            if not r.passed and "critical" in r.check_name.lower()
        ]
