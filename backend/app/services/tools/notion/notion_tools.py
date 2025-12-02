"""
Notion Tools

Read-only tools for Notion workspace integration.
Initially supports: search, read pages, read databases.

Future extensions (when needed):
- CreatePageTool
- UpdatePageTool
- UpdateDatabaseTool
"""
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class NotionSearchTool(MindscapeTool):
    """Search pages and databases in Notion workspace"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"

        metadata = ToolMetadata(
            name="notion_search",
            description="Search pages and databases in Notion workspace",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "filter": {
                        "type": "object",
                        "description": "Filter options (optional)",
                        "properties": {
                            "value": {
                                "type": "string",
                                "enum": ["page", "database"]
                            },
                            "property": {
                                "type": "string",
                                "enum": ["object"]
                            }
                        }
                    },
                    "sort": {
                        "type": "object",
                        "description": "Sort options (optional)"
                    }
                },
                required=["query"]
            ),
            category="data",
            source_type="builtin",
            provider="notion",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        query: str,
        filter: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search Notion workspace"""
        url = f"{self.base_url}/search"

        payload = {
            "query": query
        }

        if filter:
            payload["filter"] = filter
        if sort:
            payload["sort"] = sort

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Notion API error: {response.status} - {error_text}")

                    result = await response.json()
                    return {
                        "query": query,
                        "results": result.get("results", []),
                        "has_more": result.get("has_more", False),
                        "next_cursor": result.get("next_cursor")
                    }
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to connect to Notion API: {str(e)}")


class NotionReadPageTool(MindscapeTool):
    """Read content from a Notion page"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"

        metadata = ToolMetadata(
            name="notion_read_page",
            description="Read content from a Notion page by page ID",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "page_id": {
                        "type": "string",
                        "description": "Notion page ID (UUID format)"
                    }
                },
                required=["page_id"]
            ),
            category="data",
            source_type="builtin",
            provider="notion",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self, page_id: str) -> Dict[str, Any]:
        """Read Notion page"""
        url = f"{self.base_url}/pages/{page_id}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Notion API error: {response.status} - {error_text}")

                    page_data = await response.json()

                    return {
                        "page_id": page_id,
                        "properties": page_data.get("properties", {}),
                        "created_time": page_data.get("created_time"),
                        "last_edited_time": page_data.get("last_edited_time"),
                        "url": page_data.get("url"),
                        "archived": page_data.get("archived", False)
                    }
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to connect to Notion API: {str(e)}")


class NotionReadDatabaseTool(MindscapeTool):
    """Read database structure and query database entries"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"

        metadata = ToolMetadata(
            name="notion_read_database",
            description="Read database structure and query database entries",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "database_id": {
                        "type": "string",
                        "description": "Notion database ID (UUID format)"
                    },
                    "filter": {
                        "type": "object",
                        "description": "Query filter (optional, for querying entries)"
                    },
                    "sorts": {
                        "type": "array",
                        "description": "Sort options (optional, for querying entries)"
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Number of results to return (max 100)",
                        "default": 100
                    }
                },
                required=["database_id"]
            ),
            category="data",
            source_type="builtin",
            provider="notion",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        database_id: str,
        filter: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Read Notion database"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                if filter or sorts:
                    url = f"{self.base_url}/databases/{database_id}/query"
                    payload = {
                        "page_size": min(page_size, 100)
                    }
                    if filter:
                        payload["filter"] = filter
                    if sorts:
                        payload["sorts"] = sorts

                    async with session.post(url, json=payload, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise ValueError(f"Notion API error: {response.status} - {error_text}")

                        result = await response.json()
                        return {
                            "database_id": database_id,
                            "results": result.get("results", []),
                            "has_more": result.get("has_more", False),
                            "next_cursor": result.get("next_cursor")
                        }
                else:
                    url = f"{self.base_url}/databases/{database_id}"
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise ValueError(f"Notion API error: {response.status} - {error_text}")

                        db_data = await response.json()
                        return {
                            "database_id": database_id,
                            "title": db_data.get("title", []),
                            "properties": db_data.get("properties", {}),
                            "created_time": db_data.get("created_time"),
                            "last_edited_time": db_data.get("last_edited_time"),
                            "url": db_data.get("url")
                        }
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to connect to Notion API: {str(e)}")
