"""
Slack Tools

Tools for Slack workspace integration.
Supports: send messages, read channels, list channels, upload files.
"""
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class SlackSendMessageTool(MindscapeTool):
    """Send message to Slack channel"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://slack.com/api"

        metadata = ToolMetadata(
            name="slack_send_message",
            description="Send a message to a Slack channel",
            input_schema=ToolInputSchema(
                type="object",
                properties={
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
                required=["channel", "text"]
            ),
            category="communication",
            source_type="builtin",
            provider="slack",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send message to Slack channel"""
        url = f"{self.base_url}/chat.postMessage"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "channel": channel,
            "text": text
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Slack API error: {response.status} - {error_text}")

                result = await response.json()

                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    raise Exception(f"Slack API error: {error}")

                return {
                    "success": True,
                    "ts": result.get("ts"),
                    "channel": result.get("channel"),
                    "message": result.get("message")
                }


class SlackReadChannelTool(MindscapeTool):
    """Read messages from Slack channel"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://slack.com/api"

        metadata = ToolMetadata(
            name="slack_read_channel",
            description="Read messages from a Slack channel",
            input_schema=ToolInputSchema(
                type="object",
                properties={
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
                required=["channel"]
            ),
            category="communication",
            source_type="builtin",
            provider="slack",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        channel: str,
        limit: int = 100,
        oldest: Optional[str] = None,
        latest: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read messages from Slack channel"""
        url = f"{self.base_url}/conversations.history"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "channel": channel,
            "limit": min(limit, 1000)
        }

        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Slack API error: {response.status} - {error_text}")

                result = await response.json()

                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    raise Exception(f"Slack API error: {error}")

                return {
                    "success": True,
                    "messages": result.get("messages", []),
                    "has_more": result.get("has_more", False)
                }


class SlackListChannelsTool(MindscapeTool):
    """List channels in Slack workspace"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://slack.com/api"

        metadata = ToolMetadata(
            name="slack_list_channels",
            description="List channels in Slack workspace",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "types": {
                        "type": "string",
                        "description": "Comma-separated list of channel types (public_channel, private_channel, mpim, im)",
                        "default": "public_channel"
                    },
                    "exclude_archived": {
                        "type": "boolean",
                        "description": "Exclude archived channels",
                        "default": True
                    }
                },
                required=[]
            ),
            category="communication",
            source_type="builtin",
            provider="slack",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        types: str = "public_channel",
        exclude_archived: bool = True
    ) -> Dict[str, Any]:
        """List channels in Slack workspace"""
        url = f"{self.base_url}/conversations.list"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "types": types,
            "exclude_archived": exclude_archived
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Slack API error: {response.status} - {error_text}")

                result = await response.json()

                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    raise Exception(f"Slack API error: {error}")

                return {
                    "success": True,
                    "channels": result.get("channels", [])
                }


class SlackUploadFileTool(MindscapeTool):
    """Upload file to Slack channel"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://slack.com/api"

        metadata = ToolMetadata(
            name="slack_upload_file",
            description="Upload a file to a Slack channel",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "channels": {
                        "type": "string",
                        "description": "Comma-separated list of channel IDs where the file will be shared"
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
                required=["channels", "file", "filename"]
            ),
            category="communication",
            source_type="builtin",
            provider="slack",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        channels: str,
        file: str,
        filename: str,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload file to Slack channel"""
        url = f"{self.base_url}/files.upload"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        data = aiohttp.FormData()
        data.add_field("channels", channels)
        data.add_field("file", file, filename=filename)

        if title:
            data.add_field("title", title)
        if initial_comment:
            data.add_field("initial_comment", initial_comment)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Slack API error: {response.status} - {error_text}")

                result = await response.json()

                if not result.get("ok"):
                    error = result.get("error", "Unknown error")
                    raise Exception(f"Slack API error: {error}")

                return {
                    "success": True,
                    "file": result.get("file")
                }


def create_slack_tools(access_token: str) -> List[MindscapeTool]:
    """Create all Slack tools for a connection"""
    return [
        SlackSendMessageTool(access_token),
        SlackReadChannelTool(access_token),
        SlackListChannelsTool(access_token),
        SlackUploadFileTool(access_token)
    ]


def get_slack_tool_by_name(tool_name: str, access_token: str) -> Optional[MindscapeTool]:
    """Get a specific Slack tool by name"""
    tools_map = {
        "slack_send_message": SlackSendMessageTool,
        "slack_read_channel": SlackReadChannelTool,
        "slack_list_channels": SlackListChannelsTool,
        "slack_upload_file": SlackUploadFileTool
    }

    tool_class = tools_map.get(tool_name)
    if not tool_class:
        return None

    return tool_class(access_token)

