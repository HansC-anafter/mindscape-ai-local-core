"""
Governance Tools for AI Team Management

Provides tools for:
- CLI tool detection (check if external agent CLIs are installed)
- Agent installation status management
- Agent configuration management
"""

import shutil
import subprocess
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================
# Agent CLI Mapping
# ============================================================

AGENT_CLI_MAP = {
    "openclaw": {
        "command": "openclaw",
        "package": "openclaw",
        "github_repo": "https://github.com/openclaw/openclaw",
        "install_methods": [
            {"method": "npm", "command": "npm install -g openclaw"},
            {
                "method": "github",
                "command": "npm install -g https://github.com/openclaw/openclaw",
            },
        ],
        "install_guide": """
## Install OpenClaw

OpenClaw is a powerful AI agent focused on code generation and task automation.

### Option 1: npm install
```bash
npm install -g openclaw
```

### Option 2: Install from GitHub (recommended)
```bash
npm install -g https://github.com/openclaw/openclaw
```

### Verify installation
After installation, run the following command to confirm:
```bash
openclaw --version
```
""",
    },
    "langgraph": {
        "command": "uv",
        "package": "uv",
        "install_methods": [
            {
                "method": "curl",
                "command": "curl -LsSf https://astral.sh/uv/install.sh | sh",
            },
            {"method": "pip", "command": "pip install uv"},
        ],
        "install_guide": """
## Install uv (required by LangGraph)

uv is a fast Python package manager. The LangGraph Agent requires it to manage dependencies.

### Recommended (official script)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Alternative (pip)
```bash
pip install uv
```

### Verify installation
```bash
uv --version
```
""",
    },
    "aider": {
        "command": "aider",
        "package": "aider-chat",
        "install_methods": [
            {"method": "pipx", "command": "pipx install aider-chat"},
            {"method": "pip", "command": "pip install aider-chat"},
        ],
        "install_guide": """
## Install Aider

Aider is an AI pair programming assistant.

### Recommended (pipx)
```bash
pipx install aider-chat
```

### Alternative (pip)
```bash
pip install aider-chat
```

### Verify installation
```bash
aider --version
```
""",
    },
    "codex_cli": {
        "command": "codex",
        "package": "codex-cli",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @openai/codex"},
        ],
        "install_guide": """
## Install Codex CLI

OpenAI Codex CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @openai/codex
```

### Verify installation
```bash
codex --version
```
""",
    },
    "claude_code_cli": {
        "command": "claude",
        "package": "claude-code",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @anthropic-ai/claude-code"},
        ],
        "install_guide": """
## Install Claude Code CLI

Anthropic Claude Code CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @anthropic-ai/claude-code
```

### Verify installation
```bash
claude --version
```
""",
    },
    "gemini_cli": {
        "command": "gemini",
        "package": "@anthropic-ai/gemini-cli",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @anthropic-ai/gemini-cli"},
        ],
        "install_guide": """
## Install Gemini CLI

Google Gemini CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @google/gemini-cli
```

### Verify installation
```bash
gemini --version
```
""",
    },
}


# ============================================================
# Models
# ============================================================


class CLICheckResult(BaseModel):
    """Result of CLI tool check"""

    tool: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    install_guide: Optional[str] = None
    install_methods: Optional[List[Dict[str, str]]] = None
    error: Optional[str] = None


class AgentInstallStatus(BaseModel):
    """Agent installation status"""

    agent_id: str
    status: str = Field(
        description="Status: not_installed, cli_available, installed, configured"
    )
    cli_available: bool = False
    cli_version: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    last_checked: Optional[str] = None


# ============================================================
# CLI Detection Functions
# ============================================================


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


class CLIInstallResult(BaseModel):
    """Result of CLI installation attempt"""

    agent_id: str
    success: bool
    method: str
    command_executed: str
    output: Optional[str] = None
    error: Optional[str] = None
    cli_available_after: bool = False
    version_after: Optional[str] = None


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
