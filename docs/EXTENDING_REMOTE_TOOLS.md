# Extending Remote Tools

This document describes how to implement custom remote tool providers for Mindscape AI Local Core.

## Overview

Mindscape AI Local Core provides a generic mechanism for calling remote tool services via HTTP. This allows third parties (including competitors) to build their own remote tool providers without modifying the core codebase.

## Architecture

### Core Components

1. **RemoteToolAdapter**: Generic HTTP adapter for calling remote tool services
2. **ToolConnection**: Supports `connection_type = "remote"` for remote tool connections
3. **ToolRegistry**: Registration mechanism for tools

### Extension Points

Remote tool providers should be implemented as **System Capability Packs** in the cloud repository, not in local-core.

## Implementation Guide

### 1. System Capability Pack Structure

Create a system capability pack in your cloud repository:

```
your-cloud-repo/
  capabilities/
    system/
      your_remote_tools/
        __init__.py
        manifest.yaml
        config.py
        tools.py
        routes.py          # Optional: for admin UI
        ui_schema.json     # Optional: for settings UI
```

### 2. Manifest Definition

`manifest.yaml`:

```yaml
code: your_remote_tools
display_name: "Your Remote Tools Provider"
version: "1.0.0"
type: system
description: "Remote tool provider for your service"

config:
  schema:
    - name: base_url
      type: string
      required: true
      env_var: YOUR_REMOTE_TOOLS_BASE_URL
      description: "Base URL for your remote tools service"
    - name: api_token
      type: string
      required: true
      env_var: YOUR_REMOTE_TOOLS_API_TOKEN
      secret: true
      description: "API token for authentication"

tools:
  - name: line.send_message
    provider: your-service
    backend: "your_remote_tools.tools:line_send_message"
  - name: wp.publish_post
    provider: your-service
    backend: "your_remote_tools.tools:wp_publish_post"
```

### 3. Tool Implementation

`tools.py`:

```python
"""
Tool implementations for your remote tools provider
"""
import logging
from typing import Dict, Any, List, Optional

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.adapters.remote_adapter import RemoteToolAdapter
from backend.app.services.tools.schemas import (
    create_simple_tool_metadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel
)

logger = logging.getLogger(__name__)


class RemoteLineTool(MindscapeTool):
    """LINE Remote Tool via your remote service

    Sends LINE messages through your remote tool service.
    Uses RemoteToolAdapter to call your API.
    """

    def __init__(self, connection: ToolConnection):
        """
        Initialize Remote LINE Tool

        Args:
            connection: ToolConnection instance, must contain:
                - remote_cluster_url: Your remote service URL
                - remote_connection_id: Channel ID
                - config.api_token: API authentication token (optional, can come from system config)
        """
        if connection.connection_type != "remote":
            raise ValueError(f"RemoteLineTool requires connection_type='remote', got '{connection.connection_type}'")

        if not connection.remote_cluster_url:
            raise ValueError("RemoteLineTool requires remote_cluster_url")

        if not connection.remote_connection_id:
            raise ValueError("RemoteLineTool requires remote_connection_id")

        self.cluster_url = connection.remote_cluster_url
        self.channel_id = connection.remote_connection_id
        self.api_token = connection.config.get("api_token") if connection.config else None

        self.adapter = RemoteToolAdapter()

        self.metadata = create_simple_tool_metadata(
            name="line_remote",
            display_name="LINE (Remote)",
            description="Send LINE messages via remote service",
            category=ToolCategory.SOCIAL_MEDIA,
            source_type=ToolSourceType.REMOTE,
            danger_level=ToolDangerLevel.MEDIUM,
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient LINE user ID"},
                    "messages": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "LINE message objects"
                    }
                },
                "required": ["to", "messages"]
            }
        )

    async def execute(
        self,
        to: str,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send LINE message via remote service

        Args:
            to: Recipient LINE user ID
            messages: List of LINE message objects
            context: Execution context (tenant_id, workspace_id, etc.)

        Returns:
            Execution result
        """
        # Get API token from system config if available
        api_token = self.api_token
        if context and context.get("system_config"):
            system_config = context["system_config"]
            if isinstance(system_config, dict):
                system_api_token = system_config.get("api_token")
                if system_api_token:
                    api_token = system_api_token

        result = await self.adapter.call_remote_tool(
            cluster_url=self.cluster_url,
            tool_type="line",
            action="send_message",
            params={
                "channel_id": self.channel_id,
                "to": to,
                "messages": messages
            },
            api_token=api_token,
            context=context
        )

        if not result.get("success"):
            error_info = result.get("error", {})
            error_message = error_info.get("message", "Unknown error")
            raise RuntimeError(f"Failed to send LINE message: {error_message}")

        return result.get("result", {})
```

### 4. Configuration Management

`config.py`:

```python
"""
Configuration management for your remote tools provider
"""
import os
from typing import Optional, Dict, Any


def get_base_url() -> Optional[str]:
    """Get base URL from environment or system settings"""
    return os.getenv("YOUR_REMOTE_TOOLS_BASE_URL")


def get_api_token() -> Optional[str]:
    """Get API token from environment or system settings"""
    return os.getenv("YOUR_REMOTE_TOOLS_API_TOKEN")


def get_system_config() -> Dict[str, Any]:
    """Get system-level configuration"""
    return {
        "base_url": get_base_url(),
        "api_token": get_api_token()
    }
```

### 5. Tool Registration

Register your tools when the system pack is loaded:

```python
# In your system pack initialization
from backend.app.services.tools.registry import register_mindscape_tool
from backend.app.services.tools.base import ToolConnection

def register_your_remote_tools():
    """Register remote tools from your provider"""
    # Get system configuration
    config = get_system_config()

    # Create ToolConnection for each tool type
    line_connection = ToolConnection(
        id="system.your_remote_tools.line",
        tool_type="line",
        connection_type="remote",
        remote_cluster_url=config["base_url"],
        remote_connection_id=None,  # Set per workspace
        config={
            "api_token": config["api_token"],
            "provider": "your-service"
        }
    )

    # Register tool
    tool = RemoteLineTool(line_connection)
    register_mindscape_tool("system.your_remote_tools.line", tool)
```

## API Contract

### Request Format

Your remote service should accept requests in this format:

```
POST {base_url}/v1/tools/{tool_type}.{action}
Authorization: Bearer {api_token}
Content-Type: application/json

{
  "channel_id": "...",  # or tool-specific ID
  "to": "...",
  "messages": [...],
  "context": {
    "tenant_id": "...",
    "workspace_id": "...",
    "execution_id": "..."
  }
}
```

### Response Format

Your remote service should return responses in this format:

```json
{
  "success": true,
  "result": {
    // Tool-specific result data
  },
  "timestamp": "2025-12-03T20:00:00Z"
}
```

Or on error:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      // Additional error details
    }
  },
  "timestamp": "2025-12-03T20:00:00Z"
}
```

## Configuration Priority

1. **System-level configuration** (from system capability pack): Highest priority
2. **Connection-level configuration** (from ToolConnection.config): Fallback
3. **Environment variables**: Used if no system/connection config

## Best Practices

1. **No hardcoded URLs or tokens**: All configuration should come from environment variables or system settings
2. **Generic naming**: Use generic terms like "remote service" instead of vendor-specific names
3. **Error handling**: Provide clear error messages and proper error codes
4. **Context passing**: Always pass execution context for logging and rate limiting
5. **Documentation**: Document your API contract clearly

## Example: Minimal Remote Pack

See `example-remote-http-pack` in the cloud repository for a complete minimal example that demonstrates the pattern without vendor lock-in.

## Support

For questions or issues implementing remote tool providers, please open an issue in the Mindscape AI Local Core repository.

