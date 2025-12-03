"""
Playbook tool dependency resolution and environment variable substitution

Provides tool dependency resolution, environment variable substitution, and tool availability checking.
"""

import os
import re
from typing import Dict, Any, List, Optional
import logging

from backend.app.models.playbook import ToolDependency
from backend.app.services.tools.registry import (
    get_tool,
    get_mindscape_tool,
)
from backend.app.services.tools.adapters import (
    is_langchain_available,
    is_mcp_available,
    MCPServerManager,
)

logger = logging.getLogger(__name__)


class ToolDependencyResolver:
    """
    Tool dependency resolver

    Handles:
    1. Tool dependency configuration parsing
    2. Environment variable substitution
    3. Tool availability checking
    4. Automatic tool installation (when possible)
    """

    def __init__(self, mcp_manager: Optional[MCPServerManager] = None):
        """
        Initialize resolver

        Args:
            mcp_manager: MCP Server Manager (optional, for MCP tools)
        """
        if mcp_manager is None:
            if MCPServerManager is not None:
                self.mcp_manager = MCPServerManager()
            else:
                self.mcp_manager = None
        else:
            self.mcp_manager = mcp_manager
        self._env_var_pattern = re.compile(r'\$\{([^}]+)\}')

    def substitute_env_vars(
        self,
        config: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Substitute environment variables in configuration

        Supports syntax: ${VAR_NAME} or ${VAR_NAME:default_value}

        Args:
            config: Original configuration (may contain ${VAR})
            env_overrides: Environment variable overrides (takes precedence over system env)

        Returns:
            Configuration with substituted values
        """
        def substitute_value(value: Any) -> Any:
            if isinstance(value, str):
                matches = self._env_var_pattern.findall(value)

                for var_expr in matches:
                    if ':' in var_expr:
                        var_name, default_value = var_expr.split(':', 1)
                    else:
                        var_name = var_expr
                        default_value = None

                    env_value = None
                    if env_overrides and var_name in env_overrides:
                        env_value = env_overrides[var_name]
                    else:
                        env_value = os.getenv(var_name)

                    if env_value is None and default_value is not None:
                        env_value = default_value

                    if env_value is not None:
                        value = value.replace(f'${{{var_expr}}}', env_value)
                    else:
                        logger.warning(
                            f"Environment variable {var_name} not found, "
                            f"keeping placeholder ${{{var_expr}}}"
                        )

                return value

            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}

            elif isinstance(value, list):
                return [substitute_value(item) for item in value]

            else:
                return value

        return substitute_value(config)

    async def check_tool_availability(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Check availability of a single tool

        Args:
            tool_dep: Tool dependency declaration
            env_overrides: Environment variable overrides

        Returns:
            {
                "available": bool,
                "tool": MindscapeTool or None,
                "error": str or None,
                "can_auto_install": bool
            }
        """
        result = {
            "name": tool_dep.name,
            "type": tool_dep.type,
            "available": False,
            "tool": None,
            "error": None,
            "can_auto_install": False
        }

        try:
            if tool_dep.type == "builtin":
                tool = get_mindscape_tool(tool_dep.name)
                if tool:
                    result["available"] = True
                    result["tool"] = tool
                else:
                    result["error"] = f"Built-in tool {tool_dep.name} not registered"

            elif tool_dep.type == "langchain":
                if not is_langchain_available():
                    result["error"] = "LangChain not installed"
                    result["can_auto_install"] = True
                else:
                    tool = get_mindscape_tool(f"langchain.{tool_dep.name}")
                    if tool:
                        result["available"] = True
                        result["tool"] = tool
                    else:
                        result["can_auto_install"] = True
                        result["error"] = f"LangChain tool {tool_dep.name} not installed"

            elif tool_dep.type == "mcp":
                if not is_mcp_available():
                    result["error"] = "MCP dependencies not installed"
                    result["can_auto_install"] = False
                else:
                    server_id = tool_dep.source
                    if not server_id:
                        result["error"] = "MCP tool missing source (server ID)"
                    else:
                        if self.mcp_manager is not None:
                            tool = self.mcp_manager.get_tool_by_name(tool_dep.name)
                        else:
                            tool = None
                        if tool:
                            result["available"] = True
                            result["tool"] = tool
                        else:
                            result["can_auto_install"] = True
                            result["error"] = f"MCP server {server_id} not connected or tool not found"

        except Exception as e:
            logger.error(f"Error checking tool {tool_dep.name}: {e}")
            result["error"] = str(e)

        return result

    async def resolve_dependencies(
        self,
        tool_dependencies: List[ToolDependency],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Resolve all tool dependencies

        Args:
            tool_dependencies: List of tool dependencies
            env_overrides: Environment variable overrides

        Returns:
            {
                "available": List[Dict],      # Available tools
                "missing": List[Dict],          # Missing tools
                "can_auto_install": List[Dict], # Tools that can be auto-installed
                "errors": List[str]             # Error messages
            }
        """
        result = {
            "available": [],
            "missing": [],
            "can_auto_install": [],
            "errors": []
        }

        for tool_dep in tool_dependencies:
            tool_dep_resolved = tool_dep.copy(deep=True)
            tool_dep_resolved.config = self.substitute_env_vars(
                tool_dep.config,
                env_overrides
            )
            check_result = await self.check_tool_availability(
                tool_dep_resolved,
                env_overrides
            )

            if check_result["available"]:
                result["available"].append({
                    "name": tool_dep.name,
                    "type": tool_dep.type,
                    "tool": check_result["tool"]
                })
            else:
                missing_info = {
                    "name": tool_dep.name,
                    "type": tool_dep.type,
                    "required": tool_dep.required,
                    "error": check_result["error"]
                }

                result["missing"].append(missing_info)

                if check_result["can_auto_install"]:
                    result["can_auto_install"].append(missing_info)

                if tool_dep.required:
                    error_msg = (
                        f"Required tool {tool_dep.name} ({tool_dep.type}) unavailable: "
                        f"{check_result['error']}"
                    )
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

        return result

    async def auto_install_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Auto-install tool (when possible)

        Args:
            tool_dep: Tool dependency declaration
            env_overrides: Environment variable overrides

        Returns:
            {
                "success": bool,
                "tool": MindscapeTool or None,
                "error": str or None
            }
        """
        result = {
            "success": False,
            "tool": None,
            "error": None
        }

        try:
            if tool_dep.type == "langchain":
                result = await self._auto_install_langchain_tool(
                    tool_dep,
                    env_overrides
                )

            elif tool_dep.type == "mcp":
                result = await self._auto_install_mcp_tool(
                    tool_dep,
                    env_overrides
                )

            else:
                result["error"] = f"Tool type {tool_dep.type} does not support auto-installation"

        except Exception as e:
            logger.error(f"Auto-install tool {tool_dep.name} failed: {e}")
            result["error"] = str(e)

        return result

    async def _auto_install_langchain_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Auto-install LangChain tool"""
        from backend.app.services.tools.adapters import from_langchain
        from backend.app.services.tools.registry import register_mindscape_tool

        try:
            module_path, class_name = tool_dep.source.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            tool_class = getattr(module, class_name)

            config = self.substitute_env_vars(tool_dep.config, env_overrides)
            lc_tool = tool_class(**config)

            mindscape_tool = from_langchain(lc_tool)

            register_mindscape_tool(f"langchain.{tool_dep.name}", mindscape_tool)

            logger.info(f"Successfully installed LangChain tool: {tool_dep.name}")

            return {
                "success": True,
                "tool": mindscape_tool,
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to install LangChain tool {tool_dep.name}: {e}")
            return {
                "success": False,
                "tool": None,
                "error": str(e)
            }

    async def _auto_install_mcp_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Auto-install MCP tool (connect to MCP server)"""
        from backend.app.services.tools.adapters import MCPServerConfig, MCPTransportType

        try:
            server_id = tool_dep.source
            if not server_id:
                return {
                    "success": False,
                    "tool": None,
                    "error": "MCP tool missing source (server ID)"
                }

            if self.mcp_manager is not None:
                servers = self.mcp_manager.list_servers()
            else:
                servers = []
            existing_server = next(
                (s for s in servers if s["id"] == server_id),
                None
            )

            if not existing_server:
                return {
                    "success": False,
                    "tool": None,
                    "error": f"MCP server {server_id} not configured"
                }

            if not existing_server["connected"]:
                logger.warning(
                    f"MCP server {server_id} not connected, "
                    f"please configure and connect server first"
                )
                return {
                    "success": False,
                    "tool": None,
                    "error": f"MCP server {server_id} not connected"
                }

            if self.mcp_manager is not None:
                tool = self.mcp_manager.get_tool_by_name(tool_dep.name)
            else:
                tool = None
            if tool:
                logger.info(f"Found MCP tool: {tool_dep.name}")
                return {
                    "success": True,
                    "tool": tool,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "tool": None,
                    "error": f"Tool {tool_dep.name} not found in MCP server {server_id}"
                }

        except Exception as e:
            logger.error(f"Failed to install MCP tool {tool_dep.name}: {e}")
            return {
                "success": False,
                "tool": None,
                "error": str(e)
            }
