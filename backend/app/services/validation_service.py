"""
Validation Service for CapabilityInstaller

Provides comprehensive validation before pack installation:
- System health checks
- File format validation
- Manifest validation
- Compatibility checks
- Security checks
- Dependency verification
"""

import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from backend.app.services.validation_service_core.archive_checks import (
    validate_extracted_structure,
    validate_mindpack_file,
)
from backend.app.services.validation_service_core.compatibility_checks import (
    check_conflicts,
    check_version_compatibility,
    get_installed_packs,
    validate_compatibility,
)
from backend.app.services.validation_service_core.dependency_checks import (
    check_api_keys,
    validate_dependencies,
    verify_tool_dependencies,
)
from backend.app.services.validation_service_core.manifest_checks import (
    validate_manifest,
    validate_manifest_files,
    validate_manifest_schema,
    validate_manifest_with_script,
)
from backend.app.services.validation_service_core.security_checks import (
    check_file_permissions,
    check_path_traversal,
    validate_security,
)
from backend.app.services.validation_service_core.system_checks import (
    check_database_connection,
    check_dependency_services,
    check_directory_permissions,
    check_disk_space,
    validate_system_health,
)

logger = logging.getLogger(__name__)


class ValidationService:
    """Service for validating capability packs before installation"""

    def __init__(self, local_core_root: Path):
        """
        Initialize validation service

        Args:
            local_core_root: Local-core project root directory
        """
        self.local_core_root = local_core_root

    def validate_before_install(
        self,
        mindpack_path: Path,
        capabilities_dir: Path,
        specs_dir: Path,
        i18n_base_dir: Path,
        tool_registry=None
    ) -> Tuple[bool, Dict]:
        """
        Perform complete validation before installation

        Args:
            mindpack_path: Path to .mindpack file
            capabilities_dir: Target capabilities directory
            specs_dir: Target specs directory
            i18n_base_dir: Target i18n base directory
            tool_registry: Tool registry instance (optional)

        Returns:
            (is_valid: bool, result: dict)
            result contains:
            - errors: List[str]
            - warnings: List[str]
            - validation_stages: Dict[str, Dict]
        """
        result = {
            "errors": [],
            "warnings": [],
            "validation_stages": {}
        }

        logger.info("Phase 1: System Health Check")
        self._validate_system_health(result, capabilities_dir, specs_dir, i18n_base_dir)

        if result["errors"]:
            logger.error("System health check failed, stopping validation")
            return False, result

        logger.info("Phase 2: File Format Validation")
        mindpack_ok, mindpack_errors = self._validate_mindpack_file(mindpack_path)
        result["validation_stages"]["mindpack_file"] = {
            "ok": mindpack_ok,
            "errors": mindpack_errors
        }
        result["errors"].extend(mindpack_errors)

        if not mindpack_ok:
            return False, result

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            try:
                with tarfile.open(mindpack_path, "r:gz") as tar:
                    tar.extractall(temp_path)
            except Exception as e:
                result["errors"].append(f"Failed to extract mindpack: {e}")
                return False, result

            structure_ok, structure_errors = self._validate_extracted_structure(temp_path)
            result["validation_stages"]["structure"] = {
                "ok": structure_ok,
                "errors": structure_errors
            }
            result["errors"].extend(structure_errors)

            if not structure_ok:
                return False, result

            cap_dir = list(temp_path.iterdir())[0]
            manifest_path = cap_dir / "manifest.yaml"

            if not manifest_path.exists():
                result["errors"].append("manifest.yaml not found")
                return False, result

            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = yaml.safe_load(f)
            except Exception as e:
                result["errors"].append(f"Failed to parse manifest: {e}")
                return False, result

            logger.info("Phase 3: Manifest Validation")
            self._validate_manifest(manifest, manifest_path, cap_dir, result)

            logger.info("Phase 4: Compatibility Check")
            self._validate_compatibility(manifest, result)

            logger.info("Phase 5: Security Check")
            self._validate_security(cap_dir, result)

            logger.info("Phase 6: Dependency Verification")
            self._validate_dependencies(manifest, tool_registry, result)

        is_valid = len(result["errors"]) == 0
        return is_valid, result

    def _validate_system_health(
        self,
        result: Dict,
        capabilities_dir: Path,
        specs_dir: Path,
        i18n_base_dir: Path
    ):
        """Phase 1: System health checks"""
        validate_system_health(
            self.local_core_root,
            result,
            capabilities_dir,
            specs_dir,
            i18n_base_dir,
        )

    def _check_database_connection(self) -> Tuple[bool, List[str]]:
        """Check database connection"""
        return check_database_connection()

    def _check_directory_permissions(
        self,
        capabilities_dir: Path,
        specs_dir: Path,
        i18n_base_dir: Path
    ) -> Tuple[bool, List[str]]:
        """Check directory permissions"""
        return check_directory_permissions(
            self.local_core_root,
            capabilities_dir,
            specs_dir,
            i18n_base_dir,
        )

    def _check_dependency_services(self) -> Tuple[bool, List[str], List[str]]:
        """Check dependency services"""
        return check_dependency_services()

    def _check_disk_space(self, required_mb: int = 100) -> Tuple[bool, List[str]]:
        """Check disk space"""
        return check_disk_space(self.local_core_root, required_mb)

    def _validate_mindpack_file(self, mindpack_path: Path) -> Tuple[bool, List[str]]:
        """Validate .mindpack file format"""
        return validate_mindpack_file(mindpack_path)

    def _validate_extracted_structure(self, extracted_dir: Path) -> Tuple[bool, List[str]]:
        """Validate extracted directory structure"""
        return validate_extracted_structure(extracted_dir)

    def _validate_manifest(
        self,
        manifest: Dict,
        manifest_path: Path,
        cap_dir: Path,
        result: Dict
    ):
        """Phase 3: Manifest validation"""
        validate_manifest(
            self.local_core_root,
            manifest,
            manifest_path,
            cap_dir,
            result,
        )

    def _validate_manifest_schema(self, manifest: Dict) -> Tuple[bool, List[str]]:
        """Validate manifest schema"""
        return validate_manifest_schema(manifest)

    def _validate_manifest_files(
        self, manifest: Dict, cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate manifest file existence"""
        return validate_manifest_files(manifest, cap_dir)

    def _validate_manifest_with_script(
        self, manifest_path: Path, cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate manifest using the local-core manifest validator."""
        return validate_manifest_with_script(
            self.local_core_root,
            manifest_path,
            cap_dir,
        )

    def _validate_compatibility(self, manifest: Dict, result: Dict):
        """Phase 4: Compatibility checks"""
        validate_compatibility(self.local_core_root, manifest, result)

    def _check_version_compatibility(self, manifest: Dict) -> Tuple[bool, List[str]]:
        """Check version compatibility"""
        return check_version_compatibility(self.local_core_root, manifest)

    def _check_conflicts(
        self, manifest: Dict, installed_packs: List[str]
    ) -> Tuple[bool, List[str], List[str]]:
        """Check conflicts with installed packs"""
        return check_conflicts(manifest, installed_packs)

    def _get_installed_packs(self) -> List[str]:
        """Get list of installed pack IDs"""
        return get_installed_packs()

    def _validate_security(self, cap_dir: Path, result: Dict):
        """Phase 5: Security checks"""
        validate_security(cap_dir, result)

    def _check_path_traversal(self, cap_dir: Path) -> Tuple[bool, List[str]]:
        """Check for path traversal attacks"""
        return check_path_traversal(cap_dir)

    def _check_file_permissions(self, cap_dir: Path) -> Tuple[bool, List[str]]:
        """Check file permissions"""
        return check_file_permissions(cap_dir)

    def _validate_dependencies(
        self, manifest: Dict, tool_registry, result: Dict
    ):
        """Phase 6: Dependency verification"""
        validate_dependencies(manifest, tool_registry, result)

    def _verify_tool_dependencies(
        self, manifest: Dict, tool_registry
    ) -> Tuple[bool, List[str], List[str]]:
        """Verify tool dependencies"""
        return verify_tool_dependencies(manifest, tool_registry)

    def _check_api_keys(self, manifest: Dict) -> Tuple[bool, List[str], List[str]]:
        """Check required API keys"""
        return check_api_keys(manifest)
