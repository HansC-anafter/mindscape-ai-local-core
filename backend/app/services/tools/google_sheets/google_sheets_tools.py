"""
Google Sheets Tools

Tools for Google Sheets integration.
Supports: read range, write range, append rows, list spreadsheets.
"""
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class GoogleSheetsReadRangeTool(MindscapeTool):
    """Read data from a range in Google Sheets"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://sheets.googleapis.com/v4"

        metadata = ToolMetadata(
            name="google_sheets_read_range",
            description="Read data from a range in Google Sheets",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "Google Sheets spreadsheet ID"
                    },
                    "range": {
                        "type": "string",
                        "description": "Range to read (e.g., 'Sheet1!A1:B10' or 'A1:B10')"
                    },
                    "value_render_option": {
                        "type": "string",
                        "description": "How values should be rendered (FORMATTED_VALUE, UNFORMATTED_VALUE, FORMULA)",
                        "enum": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                        "default": "FORMATTED_VALUE"
                    },
                    "date_time_render_option": {
                        "type": "string",
                        "description": "How dates should be rendered (SERIAL_NUMBER, FORMATTED_STRING)",
                        "enum": ["SERIAL_NUMBER", "FORMATTED_STRING"],
                        "default": "FORMATTED_STRING"
                    }
                },
                required=["spreadsheet_id", "range"]
            ),
            category="data",
            source_type="builtin",
            provider="google_sheets",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        spreadsheet_id: str,
        range: str,
        value_render_option: str = "FORMATTED_VALUE",
        date_time_render_option: str = "FORMATTED_STRING"
    ) -> Dict[str, Any]:
        """Read data from a range in Google Sheets"""
        url = f"{self.base_url}/spreadsheets/{spreadsheet_id}/values/{range}"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "valueRenderOption": value_render_option,
            "dateTimeRenderOption": date_time_render_option
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Google Sheets API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "range": result.get("range"),
                    "values": result.get("values", [])
                }


class GoogleSheetsWriteRangeTool(MindscapeTool):
    """Write data to a range in Google Sheets"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://sheets.googleapis.com/v4"

        metadata = ToolMetadata(
            name="google_sheets_write_range",
            description="Write data to a range in Google Sheets",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "Google Sheets spreadsheet ID"
                    },
                    "range": {
                        "type": "string",
                        "description": "Range to write (e.g., 'Sheet1!A1:B10' or 'A1:B10')"
                    },
                    "values": {
                        "type": "array",
                        "description": "2D array of values to write (rows x columns)",
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "value_input_option": {
                        "type": "string",
                        "description": "How input data should be interpreted (RAW, USER_ENTERED)",
                        "enum": ["RAW", "USER_ENTERED"],
                        "default": "USER_ENTERED"
                    }
                },
                required=["spreadsheet_id", "range", "values"]
            ),
            category="data",
            source_type="builtin",
            provider="google_sheets",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[str]],
        value_input_option: str = "USER_ENTERED"
    ) -> Dict[str, Any]:
        """Write data to a range in Google Sheets"""
        url = f"{self.base_url}/spreadsheets/{spreadsheet_id}/values/{range}"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "valueInputOption": value_input_option
        }

        payload = {
            "values": values
        }

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, params=params, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Google Sheets API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "updated_range": result.get("updatedRange"),
                    "updated_rows": result.get("updatedRows"),
                    "updated_columns": result.get("updatedColumns"),
                    "updated_cells": result.get("updatedCells")
                }


class GoogleSheetsAppendRowsTool(MindscapeTool):
    """Append rows to a Google Sheets spreadsheet"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://sheets.googleapis.com/v4"

        metadata = ToolMetadata(
            name="google_sheets_append_rows",
            description="Append rows to a Google Sheets spreadsheet",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "Google Sheets spreadsheet ID"
                    },
                    "range": {
                        "type": "string",
                        "description": "Range to append to (e.g., 'Sheet1!A1' or 'Sheet1')"
                    },
                    "values": {
                        "type": "array",
                        "description": "2D array of values to append (rows x columns)",
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "value_input_option": {
                        "type": "string",
                        "description": "How input data should be interpreted (RAW, USER_ENTERED)",
                        "enum": ["RAW", "USER_ENTERED"],
                        "default": "USER_ENTERED"
                    },
                    "insert_data_option": {
                        "type": "string",
                        "description": "How to insert data (OVERWRITE, INSERT_ROWS)",
                        "enum": ["OVERWRITE", "INSERT_ROWS"],
                        "default": "INSERT_ROWS"
                    }
                },
                required=["spreadsheet_id", "range", "values"]
            ),
            category="data",
            source_type="builtin",
            provider="google_sheets",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[str]],
        value_input_option: str = "USER_ENTERED",
        insert_data_option: str = "INSERT_ROWS"
    ) -> Dict[str, Any]:
        """Append rows to a Google Sheets spreadsheet"""
        url = f"{self.base_url}/spreadsheets/{spreadsheet_id}/values/{range}:append"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "valueInputOption": value_input_option,
            "insertDataOption": insert_data_option
        }

        payload = {
            "values": values
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Google Sheets API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "updated_range": result.get("updates", {}).get("updatedRange"),
                    "updated_rows": result.get("updates", {}).get("updatedRows"),
                    "updated_columns": result.get("updates", {}).get("updatedColumns"),
                    "updated_cells": result.get("updates", {}).get("updatedCells")
                }


class GoogleSheetsListSpreadsheetsTool(MindscapeTool):
    """List Google Sheets spreadsheets"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com/drive/v3"

        metadata = ToolMetadata(
            name="google_sheets_list_spreadsheets",
            description="List Google Sheets spreadsheets in Google Drive",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "page_size": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 100, max: 1000)",
                        "default": 100
                    },
                    "page_token": {
                        "type": "string",
                        "description": "Page token for pagination"
                    },
                    "q": {
                        "type": "string",
                        "description": "Query string for filtering (optional)"
                    }
                },
                required=[]
            ),
            category="data",
            source_type="builtin",
            provider="google_sheets",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        q: Optional[str] = None
    ) -> Dict[str, Any]:
        """List Google Sheets spreadsheets"""
        url = f"{self.base_url}/files"

        params = {
            "q": "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        }

        if q:
            params["q"] = f"{params['q']} and {q}"

        params["pageSize"] = min(page_size, 1000)
        params["fields"] = "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)"

        if page_token:
            params["pageToken"] = page_token

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Google Drive API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "spreadsheets": result.get("files", []),
                    "next_page_token": result.get("nextPageToken")
                }


def create_google_sheets_tools(access_token: str) -> List[MindscapeTool]:
    """Create all Google Sheets tools for a connection"""
    return [
        GoogleSheetsReadRangeTool(access_token),
        GoogleSheetsWriteRangeTool(access_token),
        GoogleSheetsAppendRowsTool(access_token),
        GoogleSheetsListSpreadsheetsTool(access_token)
    ]


def get_google_sheets_tool_by_name(tool_name: str, access_token: str) -> Optional[MindscapeTool]:
    """Get a specific Google Sheets tool by name"""
    tools_map = {
        "google_sheets_read_range": GoogleSheetsReadRangeTool,
        "google_sheets_write_range": GoogleSheetsWriteRangeTool,
        "google_sheets_append_rows": GoogleSheetsAppendRowsTool,
        "google_sheets_list_spreadsheets": GoogleSheetsListSpreadsheetsTool
    }

    tool_class = tools_map.get(tool_name)
    if not tool_class:
        return None

    return tool_class(access_token)

