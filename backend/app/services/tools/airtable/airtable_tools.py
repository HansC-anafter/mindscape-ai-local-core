"""
Airtable Tools

Tools for Airtable workspace integration.
Supports: list bases, read tables, create/update/delete records.
"""
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class AirtableListBasesTool(MindscapeTool):
    """List all bases in Airtable workspace"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.airtable.com/v0"

        metadata = ToolMetadata(
            name="airtable_list_bases",
            description="List all bases in Airtable workspace",
            input_schema=ToolInputSchema(
                type="object",
                properties={},
                required=[]
            ),
            category="data",
            source_type="builtin",
            provider="airtable",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self) -> Dict[str, Any]:
        """List all bases in Airtable workspace"""
        url = f"{self.base_url}/meta/bases"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "bases": result.get("bases", [])
                }


class AirtableReadTableTool(MindscapeTool):
    """Read records from Airtable table"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.airtable.com/v0"

        metadata = ToolMetadata(
            name="airtable_read_table",
            description="Read records from an Airtable table",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "base_id": {
                        "type": "string",
                        "description": "Airtable base ID"
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Table name or table ID"
                    },
                    "max_records": {
                        "type": "integer",
                        "description": "Maximum number of records to return (default: 100, max: 100)",
                        "default": 100
                    },
                    "view": {
                        "type": "string",
                        "description": "View name or view ID (optional)"
                    },
                    "filter_by_formula": {
                        "type": "string",
                        "description": "Formula to filter records (optional)"
                    }
                },
                required=["base_id", "table_name"]
            ),
            category="data",
            source_type="builtin",
            provider="airtable",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        base_id: str,
        table_name: str,
        max_records: int = 100,
        view: Optional[str] = None,
        filter_by_formula: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read records from Airtable table"""
        url = f"{self.base_url}/{base_id}/{table_name}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        params = {
            "maxRecords": min(max_records, 100)
        }

        if view:
            params["view"] = view
        if filter_by_formula:
            params["filterByFormula"] = filter_by_formula

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "records": result.get("records", []),
                    "offset": result.get("offset")
                }


class AirtableCreateRecordTool(MindscapeTool):
    """Create a new record in Airtable table"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.airtable.com/v0"

        metadata = ToolMetadata(
            name="airtable_create_record",
            description="Create a new record in an Airtable table",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "base_id": {
                        "type": "string",
                        "description": "Airtable base ID"
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Table name or table ID"
                    },
                    "fields": {
                        "type": "object",
                        "description": "Field values for the new record"
                    }
                },
                required=["base_id", "table_name", "fields"]
            ),
            category="data",
            source_type="builtin",
            provider="airtable",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        base_id: str,
        table_name: str,
        fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new record in Airtable table"""
        url = f"{self.base_url}/{base_id}/{table_name}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "fields": fields
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "record": result
                }


class AirtableUpdateRecordTool(MindscapeTool):
    """Update an existing record in Airtable table"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.airtable.com/v0"

        metadata = ToolMetadata(
            name="airtable_update_record",
            description="Update an existing record in an Airtable table",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "base_id": {
                        "type": "string",
                        "description": "Airtable base ID"
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Table name or table ID"
                    },
                    "record_id": {
                        "type": "string",
                        "description": "Record ID to update"
                    },
                    "fields": {
                        "type": "object",
                        "description": "Field values to update"
                    }
                },
                required=["base_id", "table_name", "record_id", "fields"]
            ),
            category="data",
            source_type="builtin",
            provider="airtable",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
        fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing record in Airtable table"""
        url = f"{self.base_url}/{base_id}/{table_name}/{record_id}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "fields": fields
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "record": result
                }


class AirtableDeleteRecordTool(MindscapeTool):
    """Delete a record from Airtable table"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.airtable.com/v0"

        metadata = ToolMetadata(
            name="airtable_delete_record",
            description="Delete a record from an Airtable table",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "base_id": {
                        "type": "string",
                        "description": "Airtable base ID"
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Table name or table ID"
                    },
                    "record_id": {
                        "type": "string",
                        "description": "Record ID to delete"
                    }
                },
                required=["base_id", "table_name", "record_id"]
            ),
            category="data",
            source_type="builtin",
            provider="airtable",
            danger_level="high"
        )
        super().__init__(metadata)

    async def execute(
        self,
        base_id: str,
        table_name: str,
        record_id: str
    ) -> Dict[str, Any]:
        """Delete a record from Airtable table"""
        url = f"{self.base_url}/{base_id}/{table_name}/{record_id}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "deleted": result.get("deleted", False),
                    "id": result.get("id")
                }


def create_airtable_tools(api_key: str) -> List[MindscapeTool]:
    """Create all Airtable tools for a connection"""
    return [
        AirtableListBasesTool(api_key),
        AirtableReadTableTool(api_key),
        AirtableCreateRecordTool(api_key),
        AirtableUpdateRecordTool(api_key),
        AirtableDeleteRecordTool(api_key)
    ]


def get_airtable_tool_by_name(tool_name: str, api_key: str) -> Optional[MindscapeTool]:
    """Get a specific Airtable tool by name"""
    tools_map = {
        "airtable_list_bases": AirtableListBasesTool,
        "airtable_read_table": AirtableReadTableTool,
        "airtable_create_record": AirtableCreateRecordTool,
        "airtable_update_record": AirtableUpdateRecordTool,
        "airtable_delete_record": AirtableDeleteRecordTool
    }

    tool_class = tools_map.get(tool_name)
    if not tool_class:
        return None

    return tool_class(api_key)

