"""
Security Guardrails for Agent Skills

Provides deterministic security checks for third-party Agent Skills
prior to installation and execution.
"""

import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


# Potential malicious patterns (Command Injection, Data Exfil, Destructive)
MALICIOUS_PATTERNS = [
    # Destructive commands
    r"rm\s+-r?[fF]",
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/sd[a-z]",
    # Reverse shells and network exfiltration
    r"nc\s+-e",
    r"bash\s+-i",
    r"/dev/tcp/",
    r"wget\s+http.*\|\s*bash",
    r"curl\s+http.*\|\s*bash",
    # Unauthorized core file modifications
    r"chmod\s+777",
    r"chown\s+root",
    # Evaluators
    r"eval\s*\(",
    r"exec\s*\(",
]


class SecurityException(Exception):
    """Raised when a security violation is detected."""

    pass


class SecurityGuardrail:
    """
    Lightweight, deterministic security interceptor for Agent Skills.
    """

    @classmethod
    def verify_installation(cls, skill_content: str) -> bool:
        """
        Perform static analysis on the skill content before writing to disk.

        Args:
            skill_content: The raw markdown content of the SKILL.md file.

        Raises:
            SecurityException: If a malicious pattern is detected.

        Returns:
            True if verification passes.
        """
        # 1. Regex Pattern Matching for destructive commands
        for pattern_str in MALICIOUS_PATTERNS:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(skill_content):
                logger.warning(
                    f"Security violation detected during skill installation: matched pattern {pattern_str}"
                )
                raise SecurityException(
                    f"Installation blocked: The skill content contains potentially unsafe instructions matching rule '{pattern_str}'."
                )

        # 2. Structure Validation
        if "---" not in skill_content:
            logger.warning("Agent Skill missing YAML frontmatter.")
            raise SecurityException(
                "Installation blocked: The skill content must contain standard YAML frontmatter (---) at the beginning."
            )

        return True

    @classmethod
    def verify_execution(cls, command: str, sandbox_enabled: bool = True) -> bool:
        """
        Hook for future dynamic execution verification.

        Args:
            command: The command the agent intends to run.
            sandbox_enabled: Whether the command is isolated.

        Returns:
            True if verification passes.
        """
        # TODO: Implement dynamic runtime checks, argument validation, and context verification.
        return True
