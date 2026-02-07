"""
Agent Preflight Governance

Pre-execution checks for external agent tasks to ensure
they comply with Mindscape governance policies.

This module extends the existing playbook_preflight.py with
external agent-specific checks.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgentPreflightResult:
    """Result of an agent preflight check."""

    approved: bool
    """Whether the execution is approved."""

    risk_level: str  # "low" | "medium" | "high" | "critical"
    """Assessed risk level."""

    warnings: List[str]
    """Warning messages (execution can proceed)."""

    blockers: List[str]
    """Blocker messages (execution cannot proceed)."""

    requires_human_approval: bool = False
    """Whether human approval is required before execution."""

    suggested_mitigations: List[str] = None
    """Suggested ways to reduce risk."""

    def __post_init__(self):
        if self.suggested_mitigations is None:
            self.suggested_mitigations = []


class AgentPreflightChecker:
    """
    Performs preflight checks on external agent execution requests.

    Checks include:
    - Dangerous command patterns
    - Sensitive file access
    - Network egress risks
    - Resource exhaustion risks
    """

    # Patterns that indicate potentially dangerous operations
    DANGEROUS_PATTERNS = [
        (r"\brm\s+-rf\b", "Recursive file deletion"),
        (r"\bsudo\b", "Elevated privileges"),
        (r"\bchmod\s+777\b", "Insecure permissions"),
        (r"\bcurl\s+.*\|\s*sh\b", "Remote script execution"),
        (r"\bwget\s+.*\|\s*bash\b", "Remote script execution"),
        (r"\b/etc/passwd\b", "System file access"),
        (r"\b/etc/shadow\b", "System file access"),
        (r"\beval\s*\(", "Dynamic code execution"),
        (r"\bexec\s*\(", "Dynamic code execution"),
        (r"\bos\.system\b", "Shell command execution"),
        (r"\bsubprocess\.call\b", "Shell command execution"),
    ]

    # Skills that require extra scrutiny
    HIGH_RISK_SKILLS = [
        "bash",
        "shell",
        "terminal",
        "system",
        "docker",
        "kubernetes",
    ]

    # Skills that are generally safe
    LOW_RISK_SKILLS = [
        "file",
        "web_search",
        "read_only",
        "analysis",
    ]

    def __init__(self, policy: Optional[Dict[str, Any]] = None):
        """
        Initialize the preflight checker.

        Args:
            policy: Optional governance policy overrides
        """
        self.policy = policy or {}

    def check(
        self,
        task: str,
        allowed_skills: List[str],
        sandbox_path: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentPreflightResult:
        """
        Perform preflight checks on an agent execution request.

        Args:
            task: The task description
            allowed_skills: Skills the agent is allowed to use
            sandbox_path: Path to the execution sandbox
            context: Additional context (project_id, intent_id, etc.)

        Returns:
            AgentPreflightResult with approval status and details
        """
        warnings = []
        blockers = []
        suggested_mitigations = []

        # Check 1: Dangerous patterns in task description
        pattern_risks = self._check_dangerous_patterns(task)
        for pattern, description in pattern_risks:
            blockers.append(f"Dangerous pattern detected: {description}")
            suggested_mitigations.append(f"Remove or rephrase: '{pattern}'")

        # Check 2: High-risk skills
        high_risk_skills = [s for s in allowed_skills if s in self.HIGH_RISK_SKILLS]
        if high_risk_skills:
            warnings.append(f"High-risk skills enabled: {', '.join(high_risk_skills)}")
            suggested_mitigations.append(
                "Consider using only low-risk skills: "
                + ", ".join(self.LOW_RISK_SKILLS)
            )

        # Check 3: Sandbox path validation (now requires workspace context)
        sandbox_issues = self._check_sandbox_path(sandbox_path, context)
        blockers.extend(sandbox_issues)

        # Check 4: Resource limits
        resource_warnings = self._check_resource_limits(context or {})
        warnings.extend(resource_warnings)

        # Determine risk level
        risk_level = self._assess_risk_level(
            len(blockers), len(warnings), high_risk_skills
        )

        # Determine if human approval is required
        requires_human = (
            risk_level in ("high", "critical")
            or len(high_risk_skills) > 0
            or self.policy.get("always_require_approval", False)
        )

        return AgentPreflightResult(
            approved=len(blockers) == 0,
            risk_level=risk_level,
            warnings=warnings,
            blockers=blockers,
            requires_human_approval=requires_human,
            suggested_mitigations=suggested_mitigations,
        )

    def _check_dangerous_patterns(self, task: str) -> List[Tuple[str, str]]:
        """Check for dangerous patterns in the task description."""
        found = []
        task_lower = task.lower()

        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, task_lower):
                found.append((pattern, description))

        return found

    def _check_sandbox_path(
        self, sandbox_path: str, context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Validate the sandbox path is within workspace boundaries.

        Security Policy:
        - workspace_id is REQUIRED
        - sandbox_path MUST be under workspace's agent_sandboxes/ directory
        """
        issues = []
        context = context or {}

        # CRITICAL: workspace_id is required
        workspace_id = context.get("workspace_id")
        if not workspace_id:
            issues.append(
                "CRITICAL: workspace_id is REQUIRED for external agent execution. "
                "All agent sandboxes must be bound to a workspace."
            )
            return issues  # Early return, cannot validate path without workspace

        # Get workspace storage base from context
        workspace_storage_base = context.get("workspace_storage_base")
        if not workspace_storage_base:
            issues.append(
                "CRITICAL: workspace_storage_base is REQUIRED. "
                "Cannot validate sandbox path without workspace storage configuration."
            )
            return issues

        # Must be an absolute path
        if not sandbox_path.startswith("/"):
            issues.append("Sandbox path must be absolute")
            return issues

        # Validate path is within workspace boundaries
        from backend.app.services.external_agents.core.workspace_sandbox_resolver import (
            validate_agent_sandbox,
        )

        is_valid, error = validate_agent_sandbox(
            sandbox_path=sandbox_path,
            workspace_storage_base=workspace_storage_base,
        )

        if not is_valid:
            issues.append(f"CRITICAL: {error}")

        # Additional security: Cannot be system directories (defense in depth)
        forbidden_prefixes = [
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/var",
            "/root",
            "/home",
            "/System",
        ]

        for prefix in forbidden_prefixes:
            if sandbox_path.startswith(prefix):
                issues.append(f"Sandbox path cannot be in {prefix}")

        return issues

    def _check_resource_limits(self, context: Dict[str, Any]) -> List[str]:
        """Check resource limit warnings."""
        warnings = []

        # Check max_duration
        max_duration = context.get("max_duration", 300)
        if max_duration > 600:
            warnings.append(
                f"Long execution time ({max_duration}s) may consume excessive resources"
            )

        # Check if project has usage limits
        project_id = context.get("project_id")
        if project_id:
            # TODO: Query actual project limits
            pass

        return warnings

    def _assess_risk_level(
        self, blocker_count: int, warning_count: int, high_risk_skills: List[str]
    ) -> str:
        """Assess the overall risk level."""
        if blocker_count > 0:
            return "critical"
        if len(high_risk_skills) > 2:
            return "high"
        if len(high_risk_skills) > 0 or warning_count > 2:
            return "medium"
        return "low"


# Convenience function for quick checks
async def check_agent_preflight(
    task: str,
    allowed_skills: List[str],
    sandbox_path: str,
    context: Optional[Dict[str, Any]] = None,
) -> AgentPreflightResult:
    """
    Convenience function to perform preflight check.

    Usage:
        result = await check_agent_preflight(
            task="Build a web scraper",
            allowed_skills=["file", "web"],
            sandbox_path="/app/data/sandboxes/project_001"
        )
        if not result.approved:
            raise ValueError(f"Preflight failed: {result.blockers}")
    """
    checker = AgentPreflightChecker()
    return checker.check(task, allowed_skills, sandbox_path, context)
