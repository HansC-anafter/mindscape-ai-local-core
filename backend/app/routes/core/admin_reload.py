"""
Admin Reload API
Provides pre-restart validation (nginx -t style) and reload trigger endpoints.

Endpoints:
- POST /api/v1/admin/validate-reload: Validate before restart
- POST /api/v1/admin/trigger-reload: Trigger graceful restart (dev only)
"""

import os
import sys
import ast
import yaml
import logging
import signal
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class CapabilityValidator:
    """Validates capability manifests and API modules before restart"""

    def __init__(self, capabilities_dirs: List[Path]):
        self.capabilities_dirs = capabilities_dirs
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

    def validate_manifest_syntax(self, manifest_path: Path) -> bool:
        """Check manifest.yaml is valid YAML"""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.errors.append(
                {"type": "manifest_syntax", "path": str(manifest_path), "error": str(e)}
            )
            return False
        except Exception as e:
            self.errors.append(
                {"type": "manifest_read", "path": str(manifest_path), "error": str(e)}
            )
            return False

    def validate_python_syntax(self, py_path: Path) -> bool:
        """Check Python file has valid syntax (without executing)"""
        try:
            with open(py_path, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source)
            return True
        except SyntaxError as e:
            self.errors.append(
                {
                    "type": "python_syntax",
                    "path": str(py_path),
                    "line": e.lineno,
                    "error": str(e.msg),
                }
            )
            return False
        except Exception as e:
            self.errors.append(
                {"type": "python_read", "path": str(py_path), "error": str(e)}
            )
            return False

    def validate_api_paths(self, manifest_path: Path, manifest: Dict) -> bool:
        """Check API paths exist"""
        capability_dir = manifest_path.parent
        apis = manifest.get("apis", [])
        valid = True

        for api_def in apis:
            if not isinstance(api_def, dict):
                continue
            api_path = api_def.get("path")
            if api_path:
                full_path = capability_dir / api_path
                if not full_path.exists():
                    self.errors.append(
                        {
                            "type": "api_path_missing",
                            "manifest": str(manifest_path),
                            "path": api_path,
                            "expected": str(full_path),
                        }
                    )
                    valid = False
                else:
                    # Validate Python syntax
                    if full_path.suffix == ".py":
                        if not self.validate_python_syntax(full_path):
                            valid = False
        return valid

    def check_route_conflicts(self) -> Tuple[bool, List[Dict]]:
        """Check for route conflicts across DIFFERENT capabilities only"""
        routes: Dict[str, str] = {}  # prefix -> first capability that uses it
        conflicts: List[Dict] = []
        seen_capabilities: Set[str] = set()  # Track processed capabilities

        for cap_dir in self.capabilities_dirs:
            if not cap_dir.exists():
                continue

            for capability_path in cap_dir.iterdir():
                cap_name = capability_path.name

                # Skip non-directories, hidden, backup folders
                if not capability_path.is_dir():
                    continue
                if cap_name.startswith("_") or cap_name.startswith("."):
                    continue
                if ".__bak" in cap_name or ".bak" in cap_name:
                    continue

                # Skip if we've already processed this capability
                if cap_name in seen_capabilities:
                    continue
                seen_capabilities.add(cap_name)

                manifest_path = capability_path / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path, "r") as f:
                        manifest = yaml.safe_load(f)
                except:
                    continue

                apis = manifest.get("apis", [])
                for api_def in apis:
                    if not isinstance(api_def, dict):
                        continue

                    prefix = api_def.get("prefix", "")
                    if not prefix:
                        continue

                    # Only report conflict if DIFFERENT capability uses same prefix
                    if prefix in routes and routes[prefix] != cap_name:
                        conflicts.append(
                            {
                                "route": prefix,
                                "capability1": routes[prefix],
                                "capability2": cap_name,
                            }
                        )
                    elif prefix not in routes:
                        routes[prefix] = cap_name

        if conflicts:
            for c in conflicts:
                self.errors.append({"type": "route_conflict", **c})
            return False, conflicts
        return True, []

    def validate_all(self) -> Dict[str, Any]:
        """Run all validation checks"""
        checks = {
            "manifests": {"passed": 0, "failed": 0},
            "api_paths": {"passed": 0, "failed": 0},
            "python_syntax": {"passed": 0, "failed": 0},
            "routes": {"status": "ok"},
        }

        for cap_dir in self.capabilities_dirs:
            if not cap_dir.exists():
                self.warnings.append({"type": "dir_not_found", "path": str(cap_dir)})
                continue

            for capability_path in cap_dir.iterdir():
                if not capability_path.is_dir() or capability_path.name.startswith("_"):
                    continue

                manifest_path = capability_path / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                # Validate manifest syntax
                if self.validate_manifest_syntax(manifest_path):
                    checks["manifests"]["passed"] += 1

                    # Load and validate API paths
                    try:
                        with open(manifest_path, "r") as f:
                            manifest = yaml.safe_load(f)
                        if self.validate_api_paths(manifest_path, manifest):
                            checks["api_paths"]["passed"] += 1
                        else:
                            checks["api_paths"]["failed"] += 1
                    except:
                        checks["api_paths"]["failed"] += 1
                else:
                    checks["manifests"]["failed"] += 1

        # Check route conflicts
        routes_valid, conflicts = self.check_route_conflicts()
        if not routes_valid:
            checks["routes"] = {"status": "conflict", "conflicts": conflicts}

        # Count Python syntax checks
        syntax_errors = [e for e in self.errors if e["type"] == "python_syntax"]
        checks["python_syntax"]["failed"] = len(syntax_errors)

        valid = len(self.errors) == 0

        return {
            "valid": valid,
            "checks": checks,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@router.post("/validate-reload")
async def validate_reload():
    """
    Validate all capability manifests and API modules before restart.
    Similar to 'nginx -t' - checks syntax without restarting.

    Only validates INSTALLED capabilities (not source directories).

    Returns:
        {
            "valid": bool,
            "checks": {...},
            "errors": [...],
            "warnings": [...]
        }
    """
    # Only validate installed capabilities, not source directories
    # This prevents false positive conflicts from same pack in both locations
    local_capabilities = Path("/app/backend/app/capabilities")

    capabilities_dirs = [local_capabilities]
    # Note: We intentionally don't include MINDSCAPE_REMOTE_CAPABILITIES_DIR
    # because that's the source, not installed location

    validator = CapabilityValidator(capabilities_dirs)
    result = validator.validate_all()

    logger.info(
        f"Validation result: valid={result['valid']}, "
        f"errors={len(result['errors'])}, warnings={len(result['warnings'])}"
    )

    return result


@router.post("/trigger-reload")
async def trigger_reload(validate_first: bool = True):
    """
    Trigger graceful uvicorn reload (dev mode only).

    In production, use orchestrator-based restart (k8s, docker compose).

    Args:
        validate_first: If True, run validation before triggering reload

    Returns:
        {"triggered": bool, "message": str}
    """
    env = os.getenv("ENVIRONMENT", "development")

    if env not in ("development", "dev"):
        raise HTTPException(
            status_code=403,
            detail="Reload trigger is only available in development mode. "
            "In production, use 'docker compose restart' or k8s rollout.",
        )

    if validate_first:
        # Run validation first
        local_capabilities = Path("/app/backend/app/capabilities")
        remote_capabilities_env = os.getenv("MINDSCAPE_REMOTE_CAPABILITIES_DIR")

        capabilities_dirs = [local_capabilities]
        if remote_capabilities_env:
            capabilities_dirs.append(Path(remote_capabilities_env))

        validator = CapabilityValidator(capabilities_dirs)
        result = validator.validate_all()

        if not result["valid"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Validation failed - reload aborted",
                    "errors": result["errors"],
                },
            )

    # In dev mode with --reload, touching a watched file triggers restart
    # Or we can send SIGHUP to uvicorn
    try:
        # Method 1: Touch a file in reload-dir (simpler, works with --reload)
        trigger_file = Path("/app/backend/app/capabilities/.reload_trigger")
        trigger_file.touch()

        logger.info("Reload triggered by touching .reload_trigger file")

        return {
            "triggered": True,
            "method": "file_touch",
            "message": "Reload triggered. Uvicorn will restart shortly.",
        }
    except Exception as e:
        logger.error(f"Failed to trigger reload: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger reload: {str(e)}"
        )
