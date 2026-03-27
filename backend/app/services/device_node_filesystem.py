"""
Device Node Filesystem Service

Provides file access on the host machine via Device Node's MCP HTTP endpoint.
Uses the same pattern as restart_webhook.py — JSON-RPC 2.0 over HTTP POST to /mcp.

Device Node already implements filesystem_read/write/list tools with:
- realpath symlink validation
- YAML-based permission governance (allowed/denied paths)
- Trust level enforcement (read = auto-approve, write = confirmation)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class DeviceNodeFilesystemService:
    """
    Wraps Device Node's MCP filesystem tools for backend use.

    Device Node runs on the host at http://host.docker.internal:3100
    and exposes filesystem_read, filesystem_write, filesystem_list
    via JSON-RPC 2.0 at POST /mcp.

    Usage:
        fs = get_device_node_filesystem()
        content = await fs.read_file("/path/to/file.py")
        entries = await fs.list_dir("/path/to/dir")
    """

    def __init__(self):
        self.device_node_url = os.getenv(
            "DEVICE_NODE_URL", "http://host.docker.internal:3100"
        )
        self.timeout = float(os.getenv("DEVICE_NODE_FS_TIMEOUT", "30"))

    def is_configured(self) -> bool:
        """Check if Device Node URL is configured."""
        return bool(self.device_node_url)

    async def _call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a Device Node MCP tool via HTTP.

        Args:
            tool_name: MCP tool name (e.g. "filesystem_read")
            arguments: Tool arguments

        Returns:
            Raw JSON-RPC result dict

        Raises:
            DeviceNodeError: On connection, timeout, or tool errors
        """
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mindscape-LocalCore/1.0",
            "X-Request-Source": "filesystem-service",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.device_node_url}/mcp",
                    json=mcp_request,
                    headers=headers,
                )

            result = response.json()

            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                raise DeviceNodeError(f"Device Node tool error: {error_msg}")

            return result.get("result", {})

        except httpx.ConnectError:
            raise DeviceNodeError(
                "Device Node not reachable. "
                "Start it on host with: cd device-node && npm run dev"
            )
        except httpx.TimeoutException:
            raise DeviceNodeError(f"Device Node timeout after {self.timeout}s")
        except DeviceNodeError:
            raise
        except Exception as e:
            raise DeviceNodeError(f"Device Node call failed: {e}")

    async def is_available(self) -> bool:
        """Check if Device Node is reachable."""
        if not self.is_configured():
            return False

        try:
            # Use tools/list as a lightweight health check
            mcp_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }

            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    f"{self.device_node_url}/mcp",
                    json=mcp_request,
                    headers={"Content-Type": "application/json"},
                )

            result = response.json()
            tools = result.get("result", {}).get("tools", [])
            tool_names = [t.get("name") for t in tools]
            return "filesystem_read" in tool_names

        except Exception as e:
            logger.debug(f"Device Node availability check failed: {e}")
            return False

    async def read_file(self, path: str) -> str:
        """
        Read a file from the host filesystem via Device Node.

        Args:
            path: Absolute path to the file on the host

        Returns:
            File contents as string

        Raises:
            DeviceNodeError: On connection, permission, or file-not-found errors
        """
        result = await self._call_tool("filesystem_read", {"path": path})
        # MCP response format: { content: [{ type: "text", text: "..." }] }
        content_list = result.get("content", [])
        if content_list:
            return content_list[0].get("text", "")
        return ""

    async def write_file(self, path: str, content: str) -> str:
        """
        Write content to a file on the host filesystem via Device Node.

        Note: filesystem_write has trust_level DRAFT and may require
        user confirmation via the Web Console (depending on permission config).

        Args:
            path: Absolute path to the file on the host
            content: Content to write

        Returns:
            Result message from Device Node

        Raises:
            DeviceNodeError: On connection, permission, or write errors
        """
        result = await self._call_tool(
            "filesystem_write", {"path": path, "content": content}
        )
        content_list = result.get("content", [])
        if content_list:
            return content_list[0].get("text", "")
        return ""

    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        """
        List directory contents on the host filesystem via Device Node.

        Args:
            path: Absolute path to the directory on the host

        Returns:
            List of dicts with keys: name, type, size, modified

        Raises:
            DeviceNodeError: On connection, permission, or not-found errors
        """
        result = await self._call_tool("filesystem_list", {"path": path})
        content_list = result.get("content", [])
        if content_list:
            text = content_list[0].get("text", "[]")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return []
        return []

    async def run_host_command(
        self, command: str, args: Optional[List[str]] = None
    ) -> str:
        """
        Execute a host command via Device Node shell_execute.

        This is generic host/runtime infrastructure and should only be used
        for host-level validation or discovery tasks.
        """
        result = await self._call_tool(
            "shell_execute",
            {
                "command": command,
                "args": args or [],
            },
        )
        content_list = result.get("content", [])
        if content_list:
            return content_list[0].get("text", "")
        return ""

    async def stat_paths(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Inspect one or more host filesystem paths in a single Device Node call.
        """
        unique_paths: List[str] = []
        seen = set()
        for path in paths:
            normalized = str(path or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_paths.append(normalized)

        if not unique_paths:
            return {}

        script = """
import json
import os
import pathlib
import sys

def inspect(raw_path: str) -> dict:
    expanded = os.path.expanduser(raw_path)
    path = pathlib.Path(expanded)
    exists = path.exists()
    return {
        "requested_path": raw_path,
        "resolved_path": str(path),
        "exists": exists,
        "is_directory": path.is_dir() if exists else False,
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
        "executable": os.access(path, os.X_OK),
    }

print(json.dumps({raw: inspect(raw) for raw in sys.argv[1:]}))
""".strip()

        output = await self.run_host_command(
            "python3",
            ["-c", script, *unique_paths],
        )
        try:
            data = json.loads(output or "{}")
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            raise DeviceNodeError(f"Invalid stat_paths response: {exc}")
        raise DeviceNodeError("Invalid stat_paths response from Device Node")

    async def read_file_to_sandbox(
        self,
        host_path: str,
        sandbox_dir: str,
        workspace_id: Optional[str] = None,
    ) -> str:
        """
        Read a file from host → check file type governance → write to sandbox.

        Args:
            host_path: Absolute path on the host machine
            sandbox_dir: Local sandbox directory to stage the file into
            workspace_id: Optional workspace ID for file type governance

        Returns:
            Path to the file in the sandbox

        Raises:
            DeviceNodeError: On access errors
            FileTypeDeniedError: If file type is blocked by governance
        """
        from pathlib import Path as _Path
        from backend.app.services.file_type_governance import get_file_type_governance

        gov = get_file_type_governance()
        if not gov.is_allowed(host_path, workspace_id=workspace_id):
            reason = gov.get_reason(host_path, workspace_id=workspace_id)
            raise FileTypeDeniedError(
                f"File type denied for '{_Path(host_path).name}': {reason}"
            )

        content = await self.read_file(host_path)
        sandbox_path = _Path(sandbox_dir) / _Path(host_path).name
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        sandbox_path.write_text(content, encoding="utf-8")

        logger.info(
            f"Staged file to sandbox: {host_path} → {sandbox_path}",
            extra={"workspace_id": workspace_id},
        )
        return str(sandbox_path)


class DeviceNodeError(Exception):
    """Raised when Device Node communication fails."""

    pass


class FileTypeDeniedError(Exception):
    """Raised when a file type is blocked by governance policy."""

    pass


# Singleton
_service: Optional[DeviceNodeFilesystemService] = None


def get_device_node_filesystem() -> DeviceNodeFilesystemService:
    """Get singleton DeviceNodeFilesystemService instance."""
    global _service
    if _service is None:
        _service = DeviceNodeFilesystemService()
    return _service
