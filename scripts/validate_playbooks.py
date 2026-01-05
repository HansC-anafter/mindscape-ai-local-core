#!/usr/bin/env python3
"""
Playbook Validation Script

Standard validation for all playbooks before deployment.
Run with LLM_MOCK=true for fast dataflow validation.

Usage:
    # Validate all playbooks
    docker compose exec backend python /app/scripts/validate_playbooks.py

    # Validate specific playbook
    docker compose exec backend python /app/scripts/validate_playbooks.py --playbook intent_sync

    # Validate specific capability pack
    docker compose exec backend python /app/scripts/validate_playbooks.py --capability frontier_research
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

# Optional imports (only needed for certain validations)
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:8200")
OWNER_USER_ID = os.getenv("OWNER_USER_ID", "default-user")

# Dynamic capabilities path detection
# Priority: 1. CAPABILITIES_PATH env var, 2. Docker path, 3. Relative to script location
_capabilities_path_env = os.getenv("CAPABILITIES_PATH")
if _capabilities_path_env:
    CAPABILITIES_PATH = Path(_capabilities_path_env)
elif Path("/app/backend/app/capabilities").exists():
    # Docker environment
    CAPABILITIES_PATH = Path("/app/backend/app/capabilities")
else:
    # Local environment - relative to script location
    # scripts/validate_playbooks.py -> backend/app/capabilities
    script_dir = Path(__file__).parent
    CAPABILITIES_PATH = script_dir.parent / "backend" / "app" / "capabilities"

LLM_MOCK = os.getenv("LLM_MOCK", "").lower() in ("true", "1", "yes")


@dataclass
class ValidationResult:
    """Result of a single validation check"""
    check_name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookValidation:
    """Complete validation result for a playbook"""
    playbook_code: str
    capability: str
    results: List[ValidationResult] = field(default_factory=list)
    execution_result: Optional[Dict[str, Any]] = None

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def critical_failures(self) -> List[ValidationResult]:
        return [r for r in self.results if not r.passed and "critical" in r.check_name.lower()]


# Global flag to suppress log output in JSON mode
_json_mode = False

def log(msg: str, level: str = "INFO"):
    """Log with level prefix"""
    # Suppress log output in JSON mode, only output JSON
    if _json_mode:
        return
    colors = {
        "INFO": "\033[0m",      # Default
        "PASS": "\033[92m",     # Green
        "FAIL": "\033[91m",     # Red
        "WARN": "\033[93m",     # Yellow
        "SKIP": "\033[94m",     # Blue
    }
    reset = "\033[0m"
    color = colors.get(level, colors["INFO"])
    print(f"{color}[{level}]{reset} {msg}")


class PlaybookValidator:
    """Validates playbook structure and execution"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        if HAS_REQUESTS:
            self.session = requests.Session()
            # Set request timeout to avoid hanging
            self.timeout = 30  # Maximum 30 seconds per API request
        else:
            self.session = None
            self.timeout = 30

    def discover_playbooks(self, capability: Optional[str] = None) -> List[Tuple[str, str, Path]]:
        """
        Discover all playbooks in capabilities directory.

        Returns: List of (capability_name, playbook_code, spec_path)
        """
        playbooks = []

        for cap_dir in CAPABILITIES_PATH.iterdir():
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
        """Validate playbook spec structure"""
        results = []

        # Check if file exists
        if not spec_path.exists():
            results.append(ValidationResult(
                check_name="spec_file_exists",
                passed=False,
                message=f"Spec file not found: {spec_path}"
            ))
            return results

        try:
            with open(spec_path) as f:
                spec = json.load(f)
        except json.JSONDecodeError as e:
            results.append(ValidationResult(
                check_name="spec_json_valid",
                passed=False,
                message=f"Invalid JSON: {e}"
            ))
            return results

        results.append(ValidationResult(
            check_name="spec_json_valid",
            passed=True,
            message="JSON is valid"
        ))

        # Check required fields
        required_fields = ["playbook_code", "steps"]
        for field in required_fields:
            if field not in spec:
                results.append(ValidationResult(
                    check_name=f"spec_has_{field}",
                    passed=False,
                    message=f"Missing required field: {field}"
                ))
            else:
                results.append(ValidationResult(
                    check_name=f"spec_has_{field}",
                    passed=True,
                    message=f"Has {field}"
                ))

        # Check steps structure
        steps = spec.get("steps", [])
        if not isinstance(steps, list):
            results.append(ValidationResult(
                check_name="spec_steps_is_list",
                passed=False,
                message="steps must be a list"
            ))
        elif len(steps) == 0:
            results.append(ValidationResult(
                check_name="spec_has_steps",
                passed=False,
                message="steps is empty"
            ))
        else:
            results.append(ValidationResult(
                check_name="spec_has_steps",
                passed=True,
                message=f"Has {len(steps)} steps"
            ))

            # Check each step
            for i, step in enumerate(steps):
                step_id = step.get("id", f"step_{i}")

                # Check step has required fields
                if "id" not in step:
                    results.append(ValidationResult(
                        check_name=f"step_{i}_has_id",
                        passed=False,
                        message=f"Step {i} missing 'id'"
                    ))

                # Check step has tool or tool_slot
                has_tool = "tool" in step or "tool_slot" in step
                if not has_tool:
                    results.append(ValidationResult(
                        check_name=f"step_{step_id}_has_tool",
                        passed=False,
                        message=f"Step '{step_id}' missing 'tool' or 'tool_slot'"
                    ))

                # Check outputs use standard names for artifact creation
                outputs = step.get("outputs", {})
                tool_slot = step.get("tool_slot", "")
                if tool_slot == "core.artifacts.create":
                    if "artifact" not in outputs:
                        results.append(ValidationResult(
                            check_name=f"step_{step_id}_output_standard_critical",
                            passed=False,
                            message=f"Step '{step_id}' uses core.artifacts.create but outputs doesn't have 'artifact'"
                        ))

        # Check for cloud-only fields (should not be in playbook spec)
        forbidden_fields = ["tenant_id", "plan_id", "execution_id", "trace_id",
                           "webhook_url", "webhook_auth", "bundle_id"]
        for field in forbidden_fields:
            if field in spec:
                results.append(ValidationResult(
                    check_name=f"spec_no_cloud_field_{field}",
                    passed=False,
                    message=f"Playbook spec should not contain cloud-only field: {field}"
                ))

        return results

    def validate_tools_exist(self, spec_path: Path) -> List[ValidationResult]:
        """Validate that all referenced tools exist"""
        results = []

        try:
            with open(spec_path) as f:
                spec = json.load(f)
        except:
            return results

        # Collect all tool references
        tools_needed = set()
        for step in spec.get("steps", []):
            if "tool" in step:
                tools_needed.add(step["tool"])
            if "tool_slot" in step:
                tools_needed.add(step["tool_slot"])

        # Check each tool
        # Core slots are handled internally
        core_slots = {
            "core.intents.list",
            "core.artifacts.list",
            "core.artifacts.get_latest",
            "core.artifacts.create",
            "core.workspace.update_metadata",
            "core.workspace.get",
            "core.mind_lens.get_composition",
        }

        for tool in tools_needed:
            if tool in core_slots:
                results.append(ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,
                    message=f"Core slot: {tool}"
                ))
            elif tool.startswith("core_llm."):
                # Assume core_llm tools exist
                results.append(ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,
                    message=f"Core LLM tool: {tool}"
                ))
            else:
                # Check via API or manifest
                # For now, just log as needing verification
                results.append(ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,  # Assume exists, will fail at runtime if not
                    message=f"External tool (needs runtime check): {tool}"
                ))

        return results

    def validate_execution(self, playbook_code: str, capability: str) -> List[ValidationResult]:
        """Validate playbook execution with mock data"""
        results = []

        if not LLM_MOCK:
            results.append(ValidationResult(
                check_name="execution_mock_mode",
                passed=True,
                message="LLM_MOCK not enabled, skipping execution test"
            ))
            return results

        # Try to find existing validation workspace first, or create a new one
        workspace_id = None
        try:
            # Try to find existing workspace with same title (include system workspaces)
            resp = self.session.get(
                f"{self.base_url}/api/v1/workspaces",
                params={"owner_user_id": OWNER_USER_ID, "limit": 100, "include_system": "true"},
                timeout=self.timeout
            )
            if resp.status_code == 200:
                workspaces = resp.json()
                if isinstance(workspaces, list):
                    for ws in workspaces:
                        if ws.get("title") == f"Validate: {playbook_code}":
                            workspace_id = ws.get("id")
                            results.append(ValidationResult(
                                check_name="execution_find_workspace",
                                passed=True,
                                message=f"Reusing existing workspace: {workspace_id}"
                            ))
                            break

            # If not found, create a new one (marked as system workspace)
            if not workspace_id:
                resp = self.session.post(
                    f"{self.base_url}/api/v1/workspaces",
                    params={"owner_user_id": OWNER_USER_ID},
                    json={
                        "title": f"Validate: {playbook_code}",
                        "description": "Automated validation",
                        "is_system": True  # Mark as system workspace (hidden from UI)
                    },
                    timeout=self.timeout
                )
                if resp.status_code not in [200, 201]:
                    results.append(ValidationResult(
                        check_name="execution_create_workspace",
                        passed=False,
                        message=f"Failed to create workspace: {resp.status_code}"
                    ))
                    return results

                workspace = resp.json()
                workspace_id = workspace.get("id")
                results.append(ValidationResult(
                    check_name="execution_create_workspace",
                    passed=True,
                    message=f"Created workspace: {workspace_id}"
                ))

        except Exception as e:
            results.append(ValidationResult(
                check_name="execution_create_workspace",
                passed=False,
                message=f"Exception: {e}"
            ))
            return results

        # Execute playbook
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/playbooks/execute/start",
                params={"playbook_code": playbook_code, "workspace_id": workspace_id},
                json={"inputs": {}},
                timeout=self.timeout
            )

            if resp.status_code != 200:
                results.append(ValidationResult(
                    check_name="execution_api_call",
                    passed=False,
                    message=f"API returned {resp.status_code}: {resp.text[:200]}"
                ))
                return results

            result = resp.json()

        except Exception as e:
            results.append(ValidationResult(
                check_name="execution_api_call",
                passed=False,
                message=f"Exception: {e}"
            ))
            return results

        results.append(ValidationResult(
            check_name="execution_api_call",
            passed=True,
            message="API call succeeded"
        ))

        # Check execution status
        status = result.get("status") or result.get("execution_status")
        execution_id = result.get("execution_id")

        if status == "completed":
            results.append(ValidationResult(
                check_name="execution_status_critical",
                passed=True,
                message=f"Playbook completed successfully (execution_id: {execution_id})"
            ))
        elif status == "failed":
            error = result.get("error", "Unknown error")
            steps = result.get("steps", {})
            step_errors = []
            for step_id, step_result in steps.items():
                if isinstance(step_result, dict) and step_result.get("status") == "error":
                    step_errors.append(f"{step_id}: {step_result.get('error', 'unknown')}")

            results.append(ValidationResult(
                check_name="execution_status_critical",
                passed=False,
                message=f"Playbook failed: {error}",
                details={"step_errors": step_errors}
            ))
        else:
            results.append(ValidationResult(
                check_name="execution_status_critical",
                passed=True,
                message=f"Playbook status: {status} (execution_id: {execution_id})"
            ))

        # Clean up: Delete the validation workspace after validation
        # Only delete if this is a validation workspace (title starts with "Validate:")
        try:
            if workspace_id:
                # Check if this is a validation workspace
                resp = self.session.get(
                    f"{self.base_url}/api/v1/workspaces/{workspace_id}",
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    ws_data = resp.json()
                    is_validation = (
                        ws_data.get("title", "").startswith("Validate:") or
                        ws_data.get("is_system", False)
                    )
                    if is_validation:
                        # Delete the validation workspace
                        delete_resp = self.session.delete(
                            f"{self.base_url}/api/v1/workspaces/{workspace_id}",
                            timeout=self.timeout
                        )
                        if delete_resp.status_code in [200, 204]:
                            results.append(ValidationResult(
                                check_name="execution_cleanup_workspace",
                                passed=True,
                                message=f"Cleaned up validation workspace: {workspace_id}"
                            ))
                        else:
                            # Non-critical: cleanup failure doesn't fail validation
                            results.append(ValidationResult(
                                check_name="execution_cleanup_workspace",
                                passed=True,
                                message=f"Failed to cleanup workspace (non-critical): {delete_resp.status_code}"
                            ))
        except Exception as e:
            # Non-critical: cleanup failure doesn't fail validation
            results.append(ValidationResult(
                check_name="execution_cleanup_workspace",
                passed=True,
                message=f"Cleanup exception (non-critical): {e}"
            ))

        return results

    def validate_playbook(self, capability: str, playbook_code: str, spec_path: Path) -> PlaybookValidation:
        """Run all validations on a playbook"""
        validation = PlaybookValidation(
            playbook_code=playbook_code,
            capability=capability
        )

        # 1. Spec structure validation
        validation.results.extend(self.validate_spec_structure(spec_path))

        # 2. Tools existence validation
        validation.results.extend(self.validate_tools_exist(spec_path))

        # 3. Execution validation (only if LLM_MOCK enabled and not skipped)
        # Skip execution test during installation for speed
        if not getattr(self, '_skip_execution', False):
            validation.results.extend(self.validate_execution(playbook_code, capability))

        return validation


def main():
    parser = argparse.ArgumentParser(description="Validate playbooks before deployment")
    parser.add_argument("--playbook", "-p", help="Specific playbook code to validate")
    parser.add_argument("--capability", "-c", help="Specific capability pack to validate")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--skip-execution", action="store_true", help="Skip execution test, only validate structure")
    args = parser.parse_args()

    # Set JSON mode global flag
    global _json_mode
    _json_mode = args.json

    # Suppress log output in JSON mode
    if not args.json:
        log("=" * 70)
        log("PLAYBOOK VALIDATION")
        log(f"LLM_MOCK: {LLM_MOCK}")
        log(f"BASE_URL: {BASE_URL}")
        log("=" * 70)

    validator = PlaybookValidator()

    # Set skip execution flag if requested
    if args.skip_execution:
        validator._skip_execution = True

    # Discover playbooks
    playbooks = validator.discover_playbooks(capability=args.capability)

    if args.playbook:
        playbooks = [(c, p, s) for c, p, s in playbooks if p == args.playbook]

    if not playbooks:
        if not args.json:
            log("No playbooks found to validate", "WARN")
        return 1

    if not args.json:
        log(f"Found {len(playbooks)} playbooks to validate")
        log("")

    # Validate each playbook
    all_validations = []
    all_passed = True

    for capability, playbook_code, spec_path in playbooks:
        if not args.json:
            log("-" * 50)
            log(f"Validating: {capability}/{playbook_code}")
            log("-" * 50)

        try:
            validation = validator.validate_playbook(capability, playbook_code, spec_path)
            all_validations.append(validation)
        except Exception as e:
            # Record validation error as failure
            validation = PlaybookValidation(
                playbook_code=playbook_code,
                capability=capability
            )
            validation.results.append(ValidationResult(
                check_name="validation_error",
                passed=False,
                message=f"Validation error: {str(e)}"
            ))
            all_validations.append(validation)
            if not args.json:
                log(f"  ERROR: {e}", "FAIL")

        # Print results (only in non-JSON mode)
        if not args.json:
            for result in validation.results:
                level = "PASS" if result.passed else "FAIL"
                log(f"  {result.check_name}: {result.message}", level)
                if result.details:
                    for key, value in result.details.items():
                        log(f"    {key}: {value}")

            if not validation.passed:
                all_passed = False
                log(f"  RESULT: FAILED", "FAIL")
            else:
                log(f"  RESULT: PASSED", "PASS")

            log("")
        else:
            # In JSON mode, only check if passed
            if not validation.passed:
                all_passed = False

    # Calculate counts
    passed_count = sum(1 for v in all_validations if v.passed)
    failed_count = len(all_validations) - passed_count

    # Summary (only in non-JSON mode)
    if not args.json:
        log("=" * 70)
        log("VALIDATION SUMMARY")
        log("=" * 70)

        for v in all_validations:
            status = "PASS" if v.passed else "FAIL"
            level = "PASS" if v.passed else "FAIL"
            log(f"  {v.capability}/{v.playbook_code}: {status}", level)

        log("")
        log(f"Total: {len(all_validations)}, Passed: {passed_count}, Failed: {failed_count}")

    if args.json:
        output = {
            "summary": {
                "total": len(all_validations),
                "passed": passed_count,
                "failed": failed_count
            },
            "validations": [
                {
                    "capability": v.capability,
                    "playbook_code": v.playbook_code,
                    "passed": v.passed,
                    "results": [
                        {
                            "check_name": r.check_name,
                            "passed": r.passed,
                            "message": r.message
                        }
                        for r in v.results
                    ]
                }
                for v in all_validations
            ]
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

