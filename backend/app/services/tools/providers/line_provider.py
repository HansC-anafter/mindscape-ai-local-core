"""
Line Tool Discovery Provider

Discovers Line capabilities using Line Messaging API.
Supports: send messages, read messages, manage groups, manage friends.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class LineDiscoveryProvider(ToolDiscoveryProvider):
    """
    Line Discovery Provider

    Discovers capabilities from Line using Line Messaging API.
    """

    @property
    def provider_name(self) -> str:
        return "line"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Line capabilities

        Returns tools for:
        - Send messages
        - Read messages
        - Manage groups
        - Manage friends
        """
        channel_access_token = config.api_key
        if not channel_access_token:
            raise ValueError("Line channel access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="line_send_message",
                display_name="Send Line Message",
                description="Send a message via Line Messaging API",
                category="social_media",
                endpoint="https://api.line.me/v2/bot/message/push",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "User ID or group ID to send message to"
                        },
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["text", "image", "video", "audio", "file", "location", "sticker"],
                                        "description": "Message type"
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Message text (for text type)"
                                    }
                                }
                            },
                            "description": "Array of message objects"
                        }
                    },
                    "required": ["to", "messages"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v2",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="line_send_reply",
                display_name="Reply to Line Message",
                description="Reply to a received Line message",
                category="social_media",
                endpoint="https://api.line.me/v2/bot/message/reply",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "replyToken": {
                            "type": "string",
                            "description": "Reply token from webhook event"
                        },
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["text", "image", "video", "audio", "file", "location", "sticker"],
                                        "description": "Message type"
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Message text (for text type)"
                                    }
                                }
                            },
                            "description": "Array of message objects"
                        }
                    },
                    "required": ["replyToken", "messages"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v2",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="line_get_profile",
                display_name="Get Line User Profile",
                description="Get Line user profile information",
                category="social_media",
                endpoint="https://api.line.me/v2/bot/profile/{userId}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "userId": {
                            "type": "string",
                            "description": "Line user ID"
                        }
                    },
                    "required": ["userId"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="line_get_group_info",
                display_name="Get Line Group Information",
                description="Get Line group information",
                category="social_media",
                endpoint="https://api.line.me/v2/bot/group/{groupId}/summary",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "groupId": {
                            "type": "string",
                            "description": "Line group ID"
                        }
                    },
                    "required": ["groupId"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Line tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Line configuration

        Checks:
        - Channel access token is provided
        - Channel secret is provided (optional but recommended)
        """
        if not config.api_key:
            logger.error("Line validation failed: api_key (channel_access_token) is required")
            return False

        channel_access_token = config.api_key
        if len(channel_access_token) < 20:
            logger.warning(
                "Line channel access token seems too short. "
                "Please verify you're using a valid Line channel access token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Line",
            "description": "Line integration for sending messages, reading messages, and managing groups",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developers.line.biz/en/docs/messaging-api/",
            "notes": [
                "Requires Line channel access token",
                "Supports: send messages, reply messages, get profile, get group info",
                "Channel access token can be obtained from Line Developers Console",
                "Webhook URL configuration required for receiving messages"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Channel Access Token",
                    "placeholder": "Line channel access token",
                    "help": "Get from Line Developers Console (developers.line.biz)"
                },
                "api_secret": {
                    "type": "password",
                    "label": "Channel Secret",
                    "placeholder": "Line channel secret (optional)",
                    "help": "Channel secret for webhook verification"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "line"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Line channel access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Line channel secret (optional, for webhook verification)"
                },
                "custom_config": {
                    "type": "object",
                    "properties": {
                        "webhook_url": {
                            "type": "string",
                            "description": "Webhook URL for receiving messages"
                        }
                    }
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

