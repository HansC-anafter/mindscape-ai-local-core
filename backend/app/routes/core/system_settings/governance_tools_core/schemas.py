"""Schemas for governance tool helpers."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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
