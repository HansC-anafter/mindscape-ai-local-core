"""
Config Assistant Agent Tools

Tools available to the Config Assistant when running in Agent mode.
These tools call governance_tools directly instead of via HTTP to avoid deadlock.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def check_agent_cli(agent_id: str) -> Dict[str, Any]:
    """
    Check if CLI for an agent is installed.

    Returns CLI availability, version, and installation guide.
    """
    from .governance_tools import check_agent_cli as _check_cli

    result = _check_cli(agent_id)
    return result.dict()


async def install_agent_cli(agent_id: str, method: str = "npm") -> Dict[str, Any]:
    """
    Install CLI for an agent using specified method.

    Args:
        agent_id: Agent ID (e.g., 'moltbot')
        method: Installation method ('npm', 'pip', 'github')

    Returns installation result with success status and output.
    """
    from .governance_tools import install_agent_cli as _install_cli

    result = _install_cli(agent_id, method)
    return result.dict()


async def install_from_github(agent_id: str, repo_url: str) -> Dict[str, Any]:
    """
    Install agent CLI from GitHub repository.

    Args:
        agent_id: Agent ID
        repo_url: GitHub repository URL

    Returns installation result.
    """
    from .governance_tools import install_agent_cli as _install_cli

    # Map agent to known GitHub repos
    KNOWN_REPOS = {
        "moltbot": "https://github.com/openclaw/openclaw",
        "aider": "https://github.com/paul-gauthier/aider",
    }

    url = repo_url or KNOWN_REPOS.get(agent_id, "")
    if not url:
        return {
            "success": False,
            "error": f"No GitHub repository known for agent: {agent_id}",
        }

    result = _install_cli(agent_id, "github")
    return result.dict()


async def enable_agent(agent_id: str) -> Dict[str, Any]:
    """
    Enable an agent after successful CLI installation.

    Args:
        agent_id: Agent ID to enable

    Returns result with enabled status.
    """
    from .governance_tools import save_agent_config, get_agent_install_status

    try:
        # Get current status
        status = get_agent_install_status(agent_id)

        # Save as enabled
        config = {
            "installed": status.cli_available,
            "configured": True,
            "enabled": True,
        }
        success = save_agent_config(agent_id, config)

        if not success:
            return {"success": False, "error": "Failed to save agent config"}

        return {
            "success": True,
            "agent_id": agent_id,
            "enabled": True,
            "message": f"Agent {agent_id} has been enabled",
        }
    except Exception as e:
        logger.error(f"Failed to enable agent {agent_id}: {e}")
        return {"success": False, "error": str(e)}


async def list_available_agents() -> Dict[str, Any]:
    """
    List all available agents and their installation status.

    Returns list of agents with status and requirements.
    """
    from .governance_tools import AGENT_CLI_MAP, get_agent_install_status

    agents = []
    for agent_id, info in AGENT_CLI_MAP.items():
        status = get_agent_install_status(agent_id)
        agents.append(
            {
                "agent_id": agent_id,
                "name": info.get("name", agent_id),
                "status": status.status,
                "cli_available": status.cli_available,
                "requirements": info.get("requirements", ""),
            }
        )

    return {"agents": agents}


async def get_agent_config(agent_id: str) -> Dict[str, Any]:
    """
    Get current configuration for an agent.

    Args:
        agent_id: Agent ID

    Returns agent configuration settings.
    """
    from .governance_tools import get_agent_config as _get_config

    config = _get_config(agent_id)
    if config:
        return config
    return {"error": f"Agent not found: {agent_id}"}


async def update_agent_config(agent_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update configuration for an agent.

    Args:
        agent_id: Agent ID
        config: New configuration settings

    Returns updated configuration.
    """
    from .governance_tools import save_agent_config

    success = save_agent_config(agent_id, config)
    if success:
        return {"success": True, "agent_id": agent_id, "config": config}
    return {"success": False, "error": "Failed to save config"}


# Tool registry for Config Assistant Agent Mode
CONFIG_ASSISTANT_TOOLS = {
    "check_agent_cli": check_agent_cli,
    "install_agent_cli": install_agent_cli,
    "install_from_github": install_from_github,
    "enable_agent": enable_agent,
    "list_available_agents": list_available_agents,
    "get_agent_config": get_agent_config,
    "update_agent_config": update_agent_config,
}


def get_config_assistant_tools() -> Dict[str, Any]:
    """Get all tools available for Config Assistant Agent Mode"""
    return CONFIG_ASSISTANT_TOOLS.copy()
