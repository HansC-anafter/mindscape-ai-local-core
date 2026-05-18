"""Compatibility facade for governance tool helpers."""

from .governance_tools_core.agent_catalog import AGENT_CLI_MAP
from .governance_tools_core.cli_checks import (
    check_agent_cli,
    check_cli_tool,
    get_all_agent_cli_status,
)
from .governance_tools_core.config_store import (
    get_agent_config,
    get_agent_install_status,
    save_agent_config,
)
from .governance_tools_core.installers import install_agent_cli
from .governance_tools_core.schemas import (
    AgentInstallStatus,
    CLICheckResult,
    CLIInstallResult,
)

__all__ = [
    "AGENT_CLI_MAP",
    "AgentInstallStatus",
    "CLICheckResult",
    "CLIInstallResult",
    "check_agent_cli",
    "check_cli_tool",
    "get_all_agent_cli_status",
    "get_agent_config",
    "get_agent_install_status",
    "install_agent_cli",
    "save_agent_config",
]
