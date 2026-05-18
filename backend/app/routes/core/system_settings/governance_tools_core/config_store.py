"""Agent governance configuration helpers."""

import logging
from typing import Any, Dict, Optional

from .cli_checks import check_agent_cli
from .schemas import AgentInstallStatus

logger = logging.getLogger(__name__)

def get_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Get stored configuration for an agent.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent configuration dict or None
    """
    from .shared import settings_store

    try:
        setting = settings_store.get_setting(f"governance.agents.{agent_id}")
        if setting:
            return setting.value if isinstance(setting.value, dict) else None
        return None
    except Exception:
        return None

def save_agent_config(agent_id: str, config: Dict[str, Any]) -> bool:
    """
    Save configuration for an agent.

    Args:
        agent_id: Agent identifier
        config: Configuration dict

    Returns:
        True if saved successfully
    """
    from .shared import settings_store
    from backend.app.models.system_settings import SettingType

    try:
        settings_store.set_setting(
            key=f"governance.agents.{agent_id}",
            value=config,
            value_type=SettingType.JSON,
            category="governance",
            description=f"Configuration for agent: {agent_id}",
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save agent config for {agent_id}: {e}")
        return False

def get_agent_install_status(agent_id: str) -> AgentInstallStatus:
    """
    Get comprehensive installation status for an agent.

    Args:
        agent_id: Agent identifier

    Returns:
        AgentInstallStatus with full status info
    """
    from datetime import datetime

    # Check CLI availability
    cli_result = check_agent_cli(agent_id)

    # Get stored config
    config = get_agent_config(agent_id)

    # Determine status
    if config and config.get("installed"):
        if config.get("configured"):
            status = "configured"
        else:
            status = "installed"
    elif cli_result.available:
        status = "cli_available"
    else:
        status = "not_installed"

    return AgentInstallStatus(
        agent_id=agent_id,
        status=status,
        cli_available=cli_result.available,
        cli_version=cli_result.version,
        config=config,
        last_checked=datetime.now().isoformat(),
    )


# ============================================================
# CLI Installation Functions
# ============================================================
