"""
Slack Tool Discovery Provider

Discovers Slack workspace capabilities using Slack API.
Supports: send messages, read channels, list channels, upload files.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class SlackDiscoveryProvider(ToolDiscoveryProvider):
    """
    Slack Discovery Provider

    Discovers capabilities from a Slack workspace using Slack API.
    """

    @property
    def provider_name(self) -> str:
        return "slack"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Slack workspace capabilities

        Returns tools for:
        - Send messages
        - Read channel messages
        - List channels
        - Upload files
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Slack access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="slack_send_message",
                display_name="Send Slack Message",
                description="Send a message to a Slack channel",
                category="communication",
                endpoint="https://slack.com/api/chat.postMessage",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel": {
                            "type": "string",
                            "description": "Channel ID or channel name (e.g., #general or C1234567890)"
                        },
                        "text": {
                            "type": "string",
                            "description": "Message text"
                        },
                        "thread_ts": {
                            "type": "string",
                            "description": "Thread timestamp (optional, for replying to a thread)"
                        }
                    },
                    "required": ["channel", "text"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v2",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="slack_read_channel",
                display_name="Read Slack Channel",
                description="Read messages from a Slack channel",
                category="communication",
                endpoint="https://slack.com/api/conversations.history",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel": {
                            "type": "string",
                            "description": "Channel ID (e.g., C1234567890)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of messages to retrieve (default: 100, max: 1000)",
                            "default": 100
                        },
                        "oldest": {
                            "type": "string",
                            "description": "Oldest message timestamp to retrieve (optional)"
                        },
                        "latest": {
                            "type": "string",
                            "description": "Latest message timestamp to retrieve (optional)"
                        }
                    },
                    "required": ["channel"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="slack_list_channels",
                display_name="List Slack Channels",
                description="List channels in Slack workspace",
                category="communication",
                endpoint="https://slack.com/api/conversations.list",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "types": {
                            "type": "string",
                            "description": "Comma-separated list of channel types",
                            "default": "public_channel"
                        },
                        "exclude_archived": {
                            "type": "boolean",
                            "description": "Exclude archived channels",
                            "default": True
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="slack_upload_file",
                display_name="Upload File to Slack",
                description="Upload a file to a Slack channel",
                category="communication",
                endpoint="https://slack.com/api/files.upload",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "channels": {
                            "type": "string",
                            "description": "Comma-separated list of channel IDs"
                        },
                        "file": {
                            "type": "string",
                            "description": "File content (base64 encoded) or file path"
                        },
                        "filename": {
                            "type": "string",
                            "description": "Filename"
                        },
                        "title": {
                            "type": "string",
                            "description": "Title of file (optional)"
                        },
                        "initial_comment": {
                            "type": "string",
                            "description": "Initial comment to add to file (optional)"
                        }
                    },
                    "required": ["channels", "file", "filename"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v2",
                    "operation": "write"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Slack tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Slack configuration

        Checks:
        - Access token is provided
        - Token format is valid (starts with 'xoxb-' for bot tokens or 'xoxp-' for user tokens)
        """
        if not config.api_key:
            logger.error("Slack validation failed: api_key (access_token) is required")
            return False

        access_token = config.api_key
        if not (access_token.startswith("xoxb-") or access_token.startswith("xoxp-")):
            logger.warning(
                "Slack access token should start with 'xoxb-' (bot token) or 'xoxp-' (user token). "
                "Please verify you're using a valid Slack token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Slack",
            "description": "Slack workspace integration for messaging and collaboration",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": [],
            "documentation_url": "https://api.slack.com/",
            "notes": [
                "Requires Slack OAuth access token (bot token or user token)",
                "Supports: send messages, read channels, list channels, upload files",
                "OAuth flow available for secure authentication"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "xoxb-... or xoxp-...",
                    "help": "Get from Slack OAuth flow or create at api.slack.com/apps"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "slack"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Slack access token (bot token xoxb- or user token xoxp-)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

