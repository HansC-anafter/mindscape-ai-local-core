from pathlib import Path
from typing import List, Optional, Tuple

from . import execution, settings
from .models import PlaybookValidation, ValidationResult
from .spec_structure import validate_spec_structure
from .tool_references import validate_tools_exist


class PlaybookValidator:
    """Validates playbook structure and execution."""

    def __init__(self, base_url: str = settings.BASE_URL):
        self.base_url = base_url
        if settings.HAS_REQUESTS:
            self.session = settings.requests.Session()
            self.timeout = 30
        else:
            self.session = None
            self.timeout = 30

    def discover_playbooks(
        self, capability: Optional[str] = None
    ) -> List[Tuple[str, str, Path]]:
        """
        Discover all playbooks in capabilities directory.

        Returns:
            List of (capability_name, playbook_code, spec_path).
        """
        playbooks = []

        for cap_dir in settings.CAPABILITIES_PATH.iterdir():
            if not cap_dir.is_dir():
                continue
            if capability and cap_dir.name != capability:
                continue

            specs_dir = cap_dir / "playbooks" / "specs"
            if not specs_dir.exists():
                continue

            for spec_file in specs_dir.glob("*.json"):
                playbook_code = spec_file.stem
                playbooks.append((cap_dir.name, playbook_code, spec_file))

        return playbooks

    def validate_spec_structure(self, spec_path: Path) -> List[ValidationResult]:
        """Validate playbook spec structure."""
        return validate_spec_structure(spec_path)

    def validate_tools_exist(self, spec_path: Path) -> List[ValidationResult]:
        """Validate that all referenced tools exist."""
        return validate_tools_exist(spec_path)

    def validate_execution(
        self, playbook_code: str, capability: str
    ) -> List[ValidationResult]:
        """Validate playbook execution with mock data."""
        return execution.validate_execution(
            session=self.session,
            timeout=self.timeout,
            base_url=self.base_url,
            playbook_code=playbook_code,
            capability=capability,
        )

    def validate_playbook(
        self, capability: str, playbook_code: str, spec_path: Path
    ) -> PlaybookValidation:
        """Run all validations on a playbook."""
        validation = PlaybookValidation(
            playbook_code=playbook_code, capability=capability
        )

        validation.results.extend(self.validate_spec_structure(spec_path))
        validation.results.extend(self.validate_tools_exist(spec_path))

        if not getattr(self, "_skip_execution", False):
            validation.results.extend(
                self.validate_execution(playbook_code, capability)
            )

        return validation
