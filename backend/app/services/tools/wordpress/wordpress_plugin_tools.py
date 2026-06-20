"""WordPress plugin endpoint MindscapeTool implementation."""

from __future__ import annotations

from typing import Any, Dict

import aiohttp

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolDangerLevel,
    ToolSourceType,
    create_simple_tool_metadata,
)
from backend.app.services.tools.wordpress.wordpress_client import (
    apply_wp_client_connection,
)


class WordPressCallPluginEndpointTool(MindscapeTool):
    """Call custom WordPress plugin endpoint."""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.call_plugin_endpoint",
            description="Call custom WordPress plugin endpoint (for SEO plugins, forms, etc.)",
            category=ToolCategory.INTEGRATION,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.MODERATE,
            properties={
                "plugin_name": {
                    "type": "string",
                    "description": "Plugin namespace (e.g., 'mindscape', 'yoast')",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Endpoint path (e.g., 'analyze', 'submit_form')",
                },
                "payload": {
                    "type": "object",
                    "description": "Request payload as JSON object",
                    "default": {},
                },
            },
            required=["plugin_name", "endpoint"],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute plugin endpoint call."""
        plugin_name = input_data["plugin_name"]
        endpoint = input_data["endpoint"]
        payload = input_data.get("payload", {})

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/{plugin_name}/v1/{endpoint}"
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    return {"success": True, "data": result}
                error_text = await response.text()
                raise Exception(
                    f"Plugin endpoint error {response.status}: {error_text}"
                )
