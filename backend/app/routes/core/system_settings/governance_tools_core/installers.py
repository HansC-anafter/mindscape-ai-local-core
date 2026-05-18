"""Agent CLI installation helpers."""

import logging
import subprocess

from .agent_catalog import AGENT_CLI_MAP
from .cli_checks import check_agent_cli
from .schemas import CLIInstallResult

logger = logging.getLogger(__name__)

def install_agent_cli(agent_id: str, method: str = "pipx") -> CLIInstallResult:
    """
    Install CLI tool for an agent.

    SECURITY: Only allows installation of whitelisted agents using predefined commands.

    Args:
        agent_id: Agent identifier (must be in AGENT_CLI_MAP)
        method: Installation method ("pipx", "pip", or "curl")

    Returns:
        CLIInstallResult with installation outcome
    """
    # Security check: only allow whitelisted agents
    if agent_id not in AGENT_CLI_MAP:
        return CLIInstallResult(
            agent_id=agent_id,
            success=False,
            method=method,
            command_executed="",
            error=f"Unknown agent: {agent_id}. Allowed agents: {', '.join(AGENT_CLI_MAP.keys())}",
        )

    agent_info = AGENT_CLI_MAP[agent_id]
    install_methods = agent_info.get("install_methods", [])

    # Find matching install method
    install_command = None
    for m in install_methods:
        if m["method"] == method:
            install_command = m["command"]
            break

    if not install_command:
        available_methods = [m["method"] for m in install_methods]
        return CLIInstallResult(
            agent_id=agent_id,
            success=False,
            method=method,
            command_executed="",
            error=f"Unknown method: {method}. Available: {', '.join(available_methods)}",
        )

    # Execute installation
    logger.info(f"Installing {agent_id} using: {install_command}")

    try:
        # Use shell=True for commands with pipes (like curl | sh)
        use_shell = "|" in install_command

        result = subprocess.run(
            install_command if use_shell else install_command.split(),
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for installations
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        if not success:
            logger.warning(f"Installation failed for {agent_id}: {output}")
            return CLIInstallResult(
                agent_id=agent_id,
                success=False,
                method=method,
                command_executed=install_command,
                output=output,
                error=f"Installation failed with code {result.returncode}",
            )

        # Verify installation
        cli_check = check_agent_cli(agent_id)

        logger.info(f"Successfully installed {agent_id}, version: {cli_check.version}")

        return CLIInstallResult(
            agent_id=agent_id,
            success=True,
            method=method,
            command_executed=install_command,
            output=output,
            cli_available_after=cli_check.available,
            version_after=cli_check.version,
        )

    except subprocess.TimeoutExpired:
        return CLIInstallResult(
            agent_id=agent_id,
            success=False,
            method=method,
            command_executed=install_command,
            error="Installation timed out after 5 minutes",
        )
    except Exception as e:
        logger.error(f"Installation error for {agent_id}: {e}")
        return CLIInstallResult(
            agent_id=agent_id,
            success=False,
            method=method,
            command_executed=install_command,
            error=str(e),
        )
