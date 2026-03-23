"""
Playbook installer and validation helpers extracted from capability_installer.py
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from .install_result import InstallResult
from .playbook_installer_core import (
    validate_playbook_required_fields,
    validate_tools_direct_call,
)

logger = logging.getLogger(__name__)


class PlaybookInstaller:
    """Install and validate playbooks (specs + markdown + tool call tests)."""

    def _install_playbooks(
        self, cap_dir: Path, capability_code: str, manifest: Dict, result: InstallResult
    ):
        """Install playbook specs and markdown files"""
        playbooks_config = manifest.get("playbooks", [])

        # Get capability installation directory
        cap_install_dir = self.capabilities_dir / capability_code
        cap_playbooks_dir = cap_install_dir / "playbooks"

        for pb_config in playbooks_config:
            playbook_code = pb_config.get("code")
            if not playbook_code:
                continue

            # Install JSON spec
            spec_path = cap_dir / pb_config.get(
                "spec_path", f"playbooks/specs/{playbook_code}.json"
            )
            if spec_path.exists():
                # Enforce required field validation before installing the spec.
                required_fields_errors = self._validate_playbook_required_fields(
                    spec_path, playbook_code
                )
                if required_fields_errors:
                    error_msg = f"Playbook {playbook_code} missing required fields: {required_fields_errors}"
                    logger.error(error_msg)
                    result.add_error(error_msg)
                    continue


                # Install to backend/playbooks/specs/ (backward compatibility)
                target_spec = self.specs_dir / f"{playbook_code}.json"
                self.specs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(spec_path, target_spec)
                result.add_installed("playbooks", playbook_code)
                logger.debug(f"Installed spec: {playbook_code}.json")

                # Also install to capabilities/{code}/playbooks/specs/ (correct location)
                cap_specs_dir = cap_playbooks_dir / "specs"
                cap_specs_dir.mkdir(parents=True, exist_ok=True)
                cap_target_spec = cap_specs_dir / f"{playbook_code}.json"
                shutil.copy2(spec_path, cap_target_spec)
                logger.debug(f"Installed spec to capability dir: {cap_target_spec}")
            else:
                # Spec file not found - log warning but don't block installation
                warning_msg = (
                    f"Playbook {playbook_code}: spec file not found: {spec_path}"
                )
                logger.warning(warning_msg)
                result.add_warning(warning_msg)

            # Install markdown files
            locales = pb_config.get("locales", ["zh-TW", "en"])
            md_path_template = pb_config.get(
                "path", f"playbooks/{{locale}}/{playbook_code}.md"
            )

            for locale in locales:
                md_path = cap_dir / md_path_template.format(locale=locale)
                if md_path.exists():
                    # Install to backend/i18n/playbooks/{locale}/ (backward compatibility)
                    target_md_dir = self.i18n_base_dir / locale
                    target_md_dir.mkdir(parents=True, exist_ok=True)
                    target_md = target_md_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, target_md)
                    logger.debug(f"Installed markdown: {playbook_code}.md ({locale})")

                    # Also install to capabilities/{code}/playbooks/{locale}/ (correct location)
                    cap_locale_dir = cap_playbooks_dir / locale
                    cap_locale_dir.mkdir(parents=True, exist_ok=True)
                    cap_target_md = cap_locale_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, cap_target_md)
                    logger.debug(
                        f"Installed markdown to capability dir: {cap_target_md}"
                    )

    def _validate_playbook_required_fields(
        self, spec_path: Path, playbook_code: str
    ) -> List[str]:
        """Validate required fields in a playbook spec."""
        _ = playbook_code
        return validate_playbook_required_fields(spec_path)

    def _validate_tools_direct_call(
        self, playbook_code: str, capability_code: str
    ) -> Tuple[List[str], List[str]]:
        """Validate tool backends without executing the playbook."""
        return validate_tools_direct_call(
            playbook_code=playbook_code,
            capability_code=capability_code,
            capabilities_dir=self.capabilities_dir,
            specs_dir=self.specs_dir,
        )
