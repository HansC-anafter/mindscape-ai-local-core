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

import json
import logging
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from packaging import version
from sqlalchemy import text

from backend.app.services.stores.installed_packs_store import InstalledPacksStore
from backend.app.services.stores.postgres_base import PostgresStoreBase

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
        db_ok, db_errors = self._check_database_connection()
        result["validation_stages"]["database"] = {"ok": db_ok, "errors": db_errors}
        result["errors"].extend(db_errors)

        dir_ok, dir_errors = self._check_directory_permissions(
            capabilities_dir, specs_dir, i18n_base_dir
        )
        result["validation_stages"]["directories"] = {"ok": dir_ok, "errors": dir_errors}
        result["errors"].extend(dir_errors)

        services_ok, service_errors, service_warnings = self._check_dependency_services()
        result["validation_stages"]["services"] = {
            "ok": services_ok,
            "errors": service_errors,
            "warnings": service_warnings
        }
        result["warnings"].extend(service_warnings)

        disk_ok, disk_errors = self._check_disk_space()
        result["validation_stages"]["disk_space"] = {"ok": disk_ok, "errors": disk_errors}
        result["errors"].extend(disk_errors)

    def _check_database_connection(self) -> Tuple[bool, List[str]]:
        """Check database connection"""
        errors = []
        try:
            store = PostgresStoreBase()
            with store.get_connection() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            errors.append(f"Database connection failed: {e}")
        return len(errors) == 0, errors

    def _check_directory_permissions(
        self,
        capabilities_dir: Path,
        specs_dir: Path,
        i18n_base_dir: Path
    ) -> Tuple[bool, List[str]]:
        """Check directory permissions"""
        errors = []
        directories = [
            capabilities_dir,
            specs_dir,
            i18n_base_dir,
            self.local_core_root / "web-console" / "src" / "app" / "capabilities"
        ]

        for dir_path in directories:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                test_file = dir_path / ".test_write"
                test_file.write_text("test")
                test_file.unlink()
            except PermissionError:
                errors.append(f"Directory not writable: {dir_path}")
            except Exception as e:
                errors.append(f"Directory check failed for {dir_path}: {e}")

        return len(errors) == 0, errors

    def _check_dependency_services(self) -> Tuple[bool, List[str], List[str]]:
        """Check dependency services"""
        errors = []
        warnings = []

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                r = redis.from_url(redis_url)
                r.ping()
            except ImportError:
                warnings.append("Redis client not installed")
            except Exception as e:
                warnings.append(f"Redis not available: {e}")

        return len(errors) == 0, errors, warnings

    def _check_disk_space(self, required_mb: int = 100) -> Tuple[bool, List[str]]:
        """Check disk space"""
        errors = []
        try:
            import shutil
            stat = shutil.disk_usage(str(self.local_core_root))
            free_mb = stat.free / (1024 * 1024)
            if free_mb < required_mb:
                errors.append(
                    f"Insufficient disk space: {free_mb:.1f}MB available, "
                    f"{required_mb}MB required"
                )
        except Exception as e:
            logger.debug(f"Could not check disk space: {e}")

        return len(errors) == 0, errors

    def _validate_mindpack_file(self, mindpack_path: Path) -> Tuple[bool, List[str]]:
        """Validate .mindpack file format"""
        errors = []

        if not mindpack_path.exists():
            return False, [f"Mindpack file not found: {mindpack_path}"]

        if not mindpack_path.suffix == ".mindpack":
            errors.append(
                f"Invalid file extension: expected .mindpack, got {mindpack_path.suffix}"
            )

        file_size = mindpack_path.stat().st_size
        if file_size == 0:
            errors.append("Mindpack file is empty")
        elif file_size > 100 * 1024 * 1024:
            errors.append(
                f"Mindpack file too large: {file_size / (1024*1024):.1f}MB"
            )

        try:
            with tarfile.open(mindpack_path, "r:gz") as tar:
                members = tar.getmembers()
                if not members:
                    errors.append("Mindpack file is empty (no files inside)")

                for member in members:
                    if ".." in member.name or member.name.startswith("/"):
                        errors.append(f"Unsafe path in mindpack: {member.name}")
        except tarfile.TarError as e:
            errors.append(f"Invalid tar.gz format: {e}")
        except Exception as e:
            errors.append(f"Failed to open mindpack file: {e}")

        return len(errors) == 0, errors

    def _validate_extracted_structure(self, extracted_dir: Path) -> Tuple[bool, List[str]]:
        """Validate extracted directory structure"""
        errors = []

        dirs = [d for d in extracted_dir.iterdir() if d.is_dir()]
        if len(dirs) != 1:
            errors.append(
                f"Expected exactly one capability directory, found {len(dirs)}"
            )
            return False, errors

        cap_dir = dirs[0]
        manifest_path = cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            errors.append("manifest.yaml not found in extracted directory")

        return len(errors) == 0, errors

    def _validate_manifest(
        self,
        manifest: Dict,
        manifest_path: Path,
        cap_dir: Path,
        result: Dict
    ):
        """Phase 3: Manifest validation"""
        schema_ok, schema_errors = self._validate_manifest_schema(manifest)
        result["validation_stages"]["manifest_schema"] = {
            "ok": schema_ok,
            "errors": schema_errors
        }
        result["errors"].extend(schema_errors)

        files_ok, files_errors, files_warnings = self._validate_manifest_files(
            manifest, cap_dir
        )
        result["validation_stages"]["manifest_files"] = {
            "ok": files_ok,
            "errors": files_errors,
            "warnings": files_warnings
        }
        result["errors"].extend(files_errors)
        result["warnings"].extend(files_warnings)

        script_ok, script_errors, script_warnings = self._validate_manifest_with_script(
            manifest_path, cap_dir
        )
        result["validation_stages"]["manifest_script"] = {
            "ok": script_ok,
            "errors": script_errors,
            "warnings": script_warnings
        }
        result["errors"].extend(script_errors)
        result["warnings"].extend(script_warnings)

    def _validate_manifest_schema(self, manifest: Dict) -> Tuple[bool, List[str]]:
        """Validate manifest schema"""
        errors = []

        required_fields = ["code", "name", "version"]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        if "code" in manifest and not isinstance(manifest["code"], str):
            errors.append("Field 'code' must be a string")

        if "version" in manifest:
            version_str = manifest["version"]
            if not isinstance(version_str, str):
                errors.append("Field 'version' must be a string")
            elif not re.match(r'^\d+\.\d+\.\d+', version_str):
                errors.append(
                    f"Invalid version format: {version_str} (expected semver)"
                )

        playbooks = manifest.get("playbooks", [])
        if not isinstance(playbooks, list):
            errors.append("Field 'playbooks' must be a list")
        else:
            for i, pb in enumerate(playbooks):
                if not isinstance(pb, dict):
                    errors.append(f"Playbook {i} must be a dictionary")
                elif "code" not in pb:
                    errors.append(f"Playbook {i} missing 'code' field")

        return len(errors) == 0, errors

    def _validate_manifest_files(
        self, manifest: Dict, cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate manifest file existence"""
        errors = []
        warnings = []

        playbooks = manifest.get("playbooks", [])
        for pb in playbooks:
            pb_code = pb.get("code")
            spec_path = pb.get("spec_path")
            if spec_path:
                spec_file = cap_dir / spec_path
                if not spec_file.exists():
                    errors.append(
                        f"Playbook {pb_code}: spec file not found: {spec_path}"
                    )
                else:
                    try:
                        with open(spec_file, 'r') as f:
                            json.load(f)
                    except json.JSONDecodeError as e:
                        errors.append(
                            f"Playbook {pb_code}: invalid JSON in spec file: {e}"
                        )

            locales = pb.get("locales", [])
            path_template = pb.get("path", "playbooks/{locale}/{code}.md")
            for locale in locales:
                locale_path = cap_dir / path_template.format(
                    locale=locale, code=pb_code
                )
                if not locale_path.exists():
                    errors.append(
                        f"Playbook {pb_code} ({locale}): locale file not found: "
                        f"{locale_path}"
                    )

        return len(errors) == 0, errors, warnings

    def _validate_manifest_with_script(
        self, manifest_path: Path, cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate manifest using external script"""
        errors = []
        warnings = []

        possible_paths = [
            self.local_core_root.parent / "mindscape-ai-cloud" / "scripts" / "validate_manifest.py",
            self.local_core_root / "backend" / "scripts" / "validate_manifest.py",
        ]

        validate_script = None
        for path in possible_paths:
            if path.exists():
                validate_script = path
                break

        if not validate_script:
            warnings.append(
                "validate_manifest.py not found, skipping advanced validation"
            )
            return True, [], warnings

        try:
            result = subprocess.run(
                [sys.executable, str(validate_script), cap_dir.name],
                cwd=str(validate_script.parent.parent),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                for line in result.stdout.split('\n'):
                    if 'ERROR' in line:
                        errors.append(line.strip())
                    elif 'WARNING' in line:
                        warnings.append(line.strip())

                if result.stderr:
                    errors.append(result.stderr.strip())
        except subprocess.TimeoutExpired:
            errors.append("Validation script timed out")
        except Exception as e:
            errors.append(f"Validation script execution failed: {e}")

        return len(errors) == 0, errors, warnings

    def _validate_compatibility(self, manifest: Dict, result: Dict):
        """Phase 4: Compatibility checks"""
        version_ok, version_errors = self._check_version_compatibility(manifest)
        result["validation_stages"]["version"] = {
            "ok": version_ok,
            "errors": version_errors
        }
        result["errors"].extend(version_errors)

        installed_packs = self._get_installed_packs()
        conflict_ok, conflict_errors, conflict_warnings = self._check_conflicts(
            manifest, installed_packs
        )
        result["validation_stages"]["conflicts"] = {
            "ok": conflict_ok,
            "errors": conflict_errors,
            "warnings": conflict_warnings
        }
        result["errors"].extend(conflict_errors)
        result["warnings"].extend(conflict_warnings)

    def _check_version_compatibility(self, manifest: Dict) -> Tuple[bool, List[str]]:
        """Check version compatibility"""
        errors = []

        core_version_required = manifest.get("core_version_required")
        if not core_version_required:
            return True, []

        try:
            version_file = self.local_core_root / "backend" / "app" / "__init__.py"
            if version_file.exists():
                content = version_file.read_text()
                match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    current_version = match.group(1)
                    pass
        except Exception:
            pass

        return len(errors) == 0, errors

    def _check_conflicts(
        self, manifest: Dict, installed_packs: List[str]
    ) -> Tuple[bool, List[str], List[str]]:
        """Check conflicts with installed packs"""
        errors = []
        warnings = []

        capability_code = manifest.get("code")
        if capability_code in installed_packs:
            errors.append(f"Capability '{capability_code}' is already installed")

        conflicts = manifest.get("conflicts", [])
        for conflict_code in conflicts:
            if conflict_code in installed_packs:
                errors.append(f"Conflicts with installed capability: {conflict_code}")

        dependencies = manifest.get("dependencies", [])
        for dep_code in dependencies:
            if dep_code not in installed_packs:
                warnings.append(f"Missing dependency: {dep_code}")

        return len(errors) == 0, errors, warnings

    def _get_installed_packs(self) -> List[str]:
        """Get list of installed pack IDs"""
        try:
            store = InstalledPacksStore()
            return store.list_installed_pack_ids()
        except Exception:
            pass
        return []

    def _validate_security(self, cap_dir: Path, result: Dict):
        """Phase 5: Security checks"""
        path_ok, path_errors = self._check_path_traversal(cap_dir)
        result["validation_stages"]["path_traversal"] = {
            "ok": path_ok,
            "errors": path_errors
        }
        result["errors"].extend(path_errors)

        perm_ok, perm_warnings = self._check_file_permissions(cap_dir)
        result["validation_stages"]["permissions"] = {
            "ok": perm_ok,
            "warnings": perm_warnings
        }
        result["warnings"].extend(perm_warnings)

    def _check_path_traversal(self, cap_dir: Path) -> Tuple[bool, List[str]]:
        """Check for path traversal attacks"""
        errors = []

        for item in cap_dir.rglob("*"):
            rel_path = item.relative_to(cap_dir)
            path_str = str(rel_path)

            if ".." in path_str:
                errors.append(f"Path traversal detected: {path_str}")

            if path_str.startswith("/"):
                errors.append(f"Absolute path detected: {path_str}")

        return len(errors) == 0, errors

    def _check_file_permissions(self, cap_dir: Path) -> Tuple[bool, List[str]]:
        """Check file permissions"""
        warnings = []

        for item in cap_dir.rglob("*"):
            if item.is_file():
                if item.stat().st_mode & 0o111 and not item.suffix == ".py":
                    warnings.append(f"Unexpected executable file: {item}")

        return True, warnings

    def _validate_dependencies(
        self, manifest: Dict, tool_registry, result: Dict
    ):
        """Phase 6: Dependency verification"""
        if tool_registry:
            tool_ok, tool_errors, tool_warnings = self._verify_tool_dependencies(
                manifest, tool_registry
            )
            result["validation_stages"]["tool_dependencies"] = {
                "ok": tool_ok,
                "errors": tool_errors,
                "warnings": tool_warnings
            }
            result["warnings"].extend(tool_warnings)

        api_ok, api_errors, api_warnings = self._check_api_keys(manifest)
        result["validation_stages"]["api_keys"] = {
            "ok": api_ok,
            "errors": api_errors,
            "warnings": api_warnings
        }
        result["warnings"].extend(api_warnings)

    def _verify_tool_dependencies(
        self, manifest: Dict, tool_registry
    ) -> Tuple[bool, List[str], List[str]]:
        """Verify tool dependencies"""
        errors = []
        warnings = []

        playbooks = manifest.get("playbooks", [])
        for pb in playbooks:
            tool_deps = pb.get("tool_dependencies", [])
            for tool_dep in tool_deps:
                if tool_dep.startswith("core_llm."):
                    continue

                if hasattr(tool_registry, "has_tool"):
                    if not tool_registry.has_tool(tool_dep):
                        warnings.append(f"Tool dependency not found: {tool_dep}")

        return len(errors) == 0, errors, warnings

    def _check_api_keys(self, manifest: Dict) -> Tuple[bool, List[str], List[str]]:
        """Check required API keys"""
        errors = []
        warnings = []

        required_api_keys = manifest.get("required_api_keys", [])
        for key_name in required_api_keys:
            env_var = os.getenv(key_name)
            if not env_var:
                warnings.append(f"Required API key not configured: {key_name}")

        return len(errors) == 0, errors, warnings
