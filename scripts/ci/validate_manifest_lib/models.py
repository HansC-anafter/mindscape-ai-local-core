from dataclasses import dataclass
from typing import List


@dataclass
class ValidationError:
    """Validation error."""

    capability: str
    field: str
    message: str
    severity: str  # "error" | "warning"


@dataclass
class ValidationResult:
    """Validation result."""

    capability: str
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
