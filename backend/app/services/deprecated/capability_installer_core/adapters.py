"""
Adapters that let the deprecated capability installer reuse modular services.
"""

from pathlib import Path
from typing import Dict, List, Tuple

from ...playbook_installer import PlaybookInstaller


class LegacyPlaybookInstallerAdapter(PlaybookInstaller):
    """Bind legacy installer paths to the modular playbook installer mixin."""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Path,
        specs_dir: Path,
        i18n_base_dir: Path,
    ):
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
        self.specs_dir = specs_dir
        self.i18n_base_dir = i18n_base_dir

    def install_playbooks(
        self, cap_dir: Path, capability_code: str, manifest: Dict, result
    ) -> None:
        """Install playbook specs and localized markdown assets."""
        self._install_playbooks(cap_dir, capability_code, manifest, result)

    def validate_playbook_required_fields(
        self, spec_path: Path, playbook_code: str
    ) -> List[str]:
        """Validate required fields in a playbook spec."""
        return self._validate_playbook_required_fields(spec_path, playbook_code)

    def validate_tools_direct_call(
        self, playbook_code: str, capability_code: str
    ) -> Tuple[List[str], List[str]]:
        """Validate tool callability for an installed playbook."""
        return self._validate_tools_direct_call(playbook_code, capability_code)
