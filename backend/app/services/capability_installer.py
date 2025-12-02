"""
Capability Installer

Tool for installing .mindpack files into local capabilities directory.
Handles validation, conflict checking, and hot-reload.
"""
import zipfile
import yaml
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class CapabilityInstaller:
    """Install .mindpack files into capabilities directory"""

    def __init__(
        self,
        capabilities_dir: Optional[Path] = None,
        user_data_dir: Optional[Path] = None
    ):
        """
        Initialize installer

        Args:
            capabilities_dir: Target capabilities directory (default: app/capabilities)
            user_data_dir: User data directory for logs (default: ./data)
        """
        if capabilities_dir is None:
            app_dir = Path(__file__).parent.parent
            capabilities_dir = app_dir / "capabilities"

        if user_data_dir is None:
            user_data_dir = Path("./data")

        self.capabilities_dir = Path(capabilities_dir)
        self.user_data_dir = Path(user_data_dir)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self.install_log_path = self.user_data_dir / "capability_installs.json"

    def install_from_file(
        self,
        package_path: Path,
        allow_overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Install capability package from backend.app.services.mindpack file

        Args:
            package_path: Path to .mindpack file
            allow_overwrite: Allow overwriting existing capability with same id+version

        Returns:
            Dict with installation results
        """
        try:
            temp_dir = Path(self.user_data_dir) / "temp_install" / datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                logger.info(f"Installing package: {package_path}")

                with zipfile.ZipFile(package_path, 'r') as zipf:
                    zipf.extractall(temp_dir)

                capability_dir = temp_dir / "capability"
                if not capability_dir.exists():
                    raise ValueError("Invalid package structure: 'capability' directory not found")

                manifest_path = capability_dir / "manifest.yaml"
                if not manifest_path.exists():
                    raise ValueError("manifest.yaml not found in package")

                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = yaml.safe_load(f)

                pack_id = manifest.get('id')
                pack_version = manifest.get('version')
                requires_core = manifest.get('requires_core', '>=0.0.0')

                if not pack_id:
                    raise ValueError("Missing 'id' in manifest")
                if not pack_version:
                    raise ValueError("Missing 'version' in manifest")

                validation_result = self._validate_manifest(manifest, pack_id, pack_version)
                if not validation_result['valid']:
                    raise ValueError(f"Manifest validation failed: {validation_result['errors']}")

                target_dir = self.capabilities_dir / pack_id.split('.')[-1]
                backup_dir = None

                # Check if already installed
                if target_dir.exists():
                    existing_manifest_path = target_dir / "manifest.yaml"
                    if existing_manifest_path.exists():
                        with open(existing_manifest_path, 'r', encoding='utf-8') as f:
                            existing_manifest = yaml.safe_load(f)
                        existing_version = existing_manifest.get('version')

                        if existing_version == pack_version and not allow_overwrite:
                            raise ValueError(
                                f"Capability {pack_id} version {pack_version} already installed. "
                                "Use allow_overwrite=True to replace."
                            )

                        # Create backup before overwriting
                        if allow_overwrite:
                            backup_dir = self.user_data_dir / "backups" / f"{pack_id.replace('.', '_')}_{existing_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            backup_dir.parent.mkdir(parents=True, exist_ok=True)
                            logger.info(f"Creating backup of existing installation: {backup_dir}")
                            shutil.copytree(target_dir, backup_dir)
                            # Remove old directory for clean install
                            shutil.rmtree(target_dir, ignore_errors=True)

                # Atomic installation: install to temporary location first, then move
                temp_target = self.capabilities_dir / f".{pack_id.split('.')[-1]}.tmp"
                if temp_target.exists():
                    shutil.rmtree(temp_target, ignore_errors=True)

                try:
                    # Copy to temporary location
                    shutil.copytree(capability_dir, temp_target)

                    # Validate installation before committing
                    temp_manifest_path = temp_target / "manifest.yaml"
                    if not temp_manifest_path.exists():
                        raise ValueError("Installation validation failed: manifest.yaml not found after copy")

                    # Atomic move: rename is atomic on most filesystems
                    if target_dir.exists():
                        shutil.rmtree(target_dir, ignore_errors=True)
                    temp_target.rename(target_dir)
                    logger.info(f"Atomic installation completed: {target_dir}")

                except Exception as e:
                    # Cleanup on failure
                    if temp_target.exists():
                        shutil.rmtree(temp_target, ignore_errors=True)
                    # Restore backup if available
                    if backup_dir and backup_dir.exists():
                        logger.warning(f"Installation failed, restoring backup from {backup_dir}")
                        if target_dir.exists():
                            shutil.rmtree(target_dir, ignore_errors=True)
                        shutil.copytree(backup_dir, target_dir)
                    raise

                self._log_installation(pack_id, pack_version, datetime.now())

                logger.info(f"Successfully installed {pack_id} v{pack_version}")
                if backup_dir:
                    logger.info(f"Previous version backed up to: {backup_dir}")

                try:
                    self._reload_capabilities()
                except Exception as reload_error:
                    logger.warning(f"Failed to reload capabilities after installation: {reload_error}")

                # Note: Role mapping will be done asynchronously in the API route
                # Store summary_for_roles in result for processing
                summary_for_roles = manifest.get('summary_for_roles')
                if summary_for_roles:
                    logger.info(f"Capability {pack_id} has summary_for_roles, will be mapped to roles after installation")

                result = {
                    "success": True,
                    "capability_id": pack_id,
                    "version": pack_version,
                    "target_dir": str(target_dir),
                    "warnings": validation_result.get('warnings', [])
                }

                if backup_dir:
                    result["backup_location"] = str(backup_dir)
                    result["was_overwrite"] = True

                return result

            finally:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Installation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _validate_manifest(
        self,
        manifest: Dict[str, Any],
        pack_id: str,
        pack_version: str
    ) -> Dict[str, Any]:
        """
        Validate manifest

        Returns:
            Dict with validation results
        """
        errors = []
        warnings = []

        if pack_id.startswith('core_'):
            errors.append(f"Package ID '{pack_id}' conflicts with core system packages")

        requires_core = manifest.get('requires_core', '>=0.0.0')
        if not self._check_version_compatibility(requires_core):
            warnings.append(f"Core version requirement '{requires_core}' may not be satisfied")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _check_version_compatibility(self, requirement: str) -> bool:
        """
        Check if core version requirement is satisfied

        Args:
            requirement: Version requirement string (e.g., ">=0.5.0")

        Returns:
            True if compatible (simplified check for now)
        """
        try:
            from packaging import version
            from packaging.specifiers import SpecifierSet

            current_version = "0.5.0"
            spec = SpecifierSet(requirement)
            return spec.contains(current_version)
        except ImportError:
            logger.warning("packaging library not available, skipping version check")
            return True
        except Exception as e:
            logger.warning(f"Version check failed: {e}")
            return True

    def _log_installation(self, pack_id: str, pack_version: str, install_time: datetime):
        """Log installation for audit trail"""
        import json

        log_entry = {
            "capability_id": pack_id,
            "version": pack_version,
            "installed_at": install_time.isoformat()
        }

        if self.install_log_path.exists():
            with open(self.install_log_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []

        logs.append(log_entry)

        with open(self.install_log_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

    def _reload_capabilities(self):
        """Reload capability registry after installation"""
        try:
            import sys
            from pathlib import Path

            app_dir = Path(__file__).parent.parent
            # In Docker: app_dir is /app/backend/app, app_dir.parent is /app/backend
            # In local: app_dir is backend/app, app_dir.parent is backend
            backend_dir = app_dir.parent

            if str(backend_dir) not in sys.path:
                sys.path.insert(0, str(backend_dir))

            from app.capabilities.registry import load_capabilities
            load_capabilities(self.capabilities_dir)
            logger.info("Capability registry reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload capability registry: {e}", exc_info=True)
            raise

    def list_installed(self) -> List[Dict[str, Any]]:
        """
        List installed capability packages

        Returns:
            List of installed capability info
        """
        installed = []

        for capability_dir in self.capabilities_dir.iterdir():
            if not capability_dir.is_dir() or capability_dir.name.startswith('_'):
                continue

            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = yaml.safe_load(f)

                # Try to load localized name and description from i18n
                display_name = manifest.get('display_name') or manifest.get('name')
                description = manifest.get('description')

                # Check if i18n files exist and try to load localized strings
                try:
                    import sys
                    from pathlib import Path
                    import os

                    app_dir = Path(__file__).parent.parent
                    # In Docker: app_dir is /app/backend/app, app_dir.parent is /app/backend
                    # In local: app_dir is backend/app, app_dir.parent is backend
                    backend_dir = app_dir.parent

                    if str(backend_dir) not in sys.path:
                        sys.path.insert(0, str(backend_dir))

                    try:
                        from app.shared.i18n_loader import load_i18n_string
                    except ImportError:
                        logger.debug("i18n_loader not available, skipping i18n loading")
                        load_i18n_string = None

                    if load_i18n_string:
                        # Try to get current locale from environment or default to zh-TW
                        # Note: In production, this should come from user profile or request context
                        current_locale = os.getenv('LOCALE', os.getenv('DEFAULT_LOCALE', 'zh-TW'))

                        capability_code = manifest.get('code', capability_dir.name)
                        pack_id = manifest.get('id', capability_code)

                        # Try to load localized manifest name
                        i18n_name = load_i18n_string(
                            f"{capability_code}.manifest.name",
                            locale=current_locale,
                            default=None
                        )
                        if i18n_name and i18n_name != f"{capability_code}.manifest.name":
                            display_name = i18n_name

                        # Try to load localized manifest description
                        i18n_desc = load_i18n_string(
                            f"{capability_code}.manifest.description",
                            locale=current_locale,
                            default=None
                        )
                        if i18n_desc and i18n_desc != f"{capability_code}.manifest.description":
                            description = i18n_desc
                except Exception as e:
                    logger.debug(f"Failed to load i18n strings for {capability_code}: {e}")

                installed.append({
                    "id": manifest.get('id') or manifest.get('code'),
                    "code": manifest.get('code'),
                    "version": manifest.get('version'),
                    "display_name": display_name,
                    "description": description,
                    "scope": manifest.get('scope', 'user'),
                    "directory": str(capability_dir)
                })
            except Exception as e:
                logger.warning(f"Failed to read manifest from {capability_dir}: {e}")

        return installed


def install_capability(
    package_path: Path,
    capabilities_dir: Optional[Path] = None,
    allow_overwrite: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to install a capability package

    Args:
        package_path: Path to .mindpack file
        capabilities_dir: Target capabilities directory
        allow_overwrite: Allow overwriting existing capability

    Returns:
        Dict with installation results
    """
    installer = CapabilityInstaller(capabilities_dir)
    return installer.install_from_file(package_path, allow_overwrite)
