"""Agent CLI detection helpers."""

import logging
import shutil
import subprocess
from typing import Dict

from .agent_catalog import AGENT_CLI_MAP
from .schemas import CLICheckResult

logger = logging.getLogger(__name__)

def check_cli_tool(tool_name: str) -> CLICheckResult:
    """
    Check if a CLI tool is installed and get its version.

    Args:
        tool_name: Name of the tool (e.g., "openclaw", "uv", "aider")

    Returns:
        CLICheckResult with availability info
    """
    # Check if command exists
    path = shutil.which(tool_name)

    if not path:
        # Tool not found, provide install guide if available
        agent_info = None
        for agent_id, info in AGENT_CLI_MAP.items():
            if info["command"] == tool_name:
                agent_info = info
                break

        return CLICheckResult(
            tool=tool_name,
            available=False,
            install_guide=agent_info["install_guide"] if agent_info else None,
            install_methods=agent_info["install_methods"] if agent_info else None,
        )

    # Tool found, try to get version
    version = None
    try:
        result = subprocess.run(
            [tool_name, "--version"], capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip() or result.stderr.strip()
        # Extract just the version number if possible
        if version:
            # Take first line only
            version = version.split("\n")[0].strip()
    except subprocess.TimeoutExpired:
        version = "timeout"
    except Exception as e:
        logger.warning(f"Failed to get version for {tool_name}: {e}")
        version = "unknown"

    return CLICheckResult(
        tool=tool_name,
        available=True,
        version=version,
        path=path,
    )

def check_agent_cli(agent_id: str) -> CLICheckResult:
    """
    Check if the CLI for a specific agent is installed.

    Args:
        agent_id: Agent identifier (e.g., "openclaw", "langgraph")

    Returns:
        CLICheckResult with availability info
    """
    if agent_id not in AGENT_CLI_MAP:
        return CLICheckResult(
            tool=agent_id,
            available=False,
            error=f"Unknown agent: {agent_id}. Known agents: {', '.join(AGENT_CLI_MAP.keys())}",
        )

    agent_info = AGENT_CLI_MAP[agent_id]
    command = agent_info["command"]

    result = check_cli_tool(command)

    # Add agent-specific install info if not available
    if not result.available:
        result.install_guide = agent_info["install_guide"]
        result.install_methods = agent_info["install_methods"]

    return result

def get_all_agent_cli_status() -> Dict[str, CLICheckResult]:
    """
    Check CLI status for all known agents.

    Returns:
        Dict mapping agent_id to CLICheckResult
    """
    results = {}
    for agent_id in AGENT_CLI_MAP:
        results[agent_id] = check_agent_cli(agent_id)
    return results


# ============================================================
# Agent Configuration Functions
# ============================================================
