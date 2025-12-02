"""
Google Drive Tools

Read-only tools for Google Drive integration.
Initially supports: list files, read files.

Future extensions (when needed):
- GoogleDriveSearchTool
- GoogleDriveCreateFileTool
- GoogleDriveUpdateFileTool
"""
import aiohttp
import logging
from typing import Dict, Any, Optional
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class GoogleDriveListFilesTool(MindscapeTool):
    """List files and folders in Google Drive"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com/drive/v3"

        metadata = ToolMetadata(
            name="google_drive_list_files",
            description="List files and folders in Google Drive",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "folder_id": {
                        "type": "string",
                        "description": "Folder ID to list (default: 'root' for root folder)",
                        "default": "root"
                    },
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
                        "description": "Query string for filtering (e.g., \"mimeType='application/pdf'\")"
                    }
                },
                required=[]
            ),
            category="data",
            source_type="builtin",
            provider="google_drive",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        folder_id: str = "root",
        page_size: int = 100,
        page_token: Optional[str] = None,
        q: Optional[str] = None
    ) -> Dict[str, Any]:
        """List files in Google Drive"""
        url = f"{self.base_url}/files"

        params = {
            "q": f"'{folder_id}' in parents and trashed=false"
        }

        if q:
            params["q"] = f"{params['q']} and {q}"

        params["pageSize"] = min(page_size, 1000)
        params["fields"] = "nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)"

        if page_token:
            params["pageToken"] = page_token

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Google Drive API error: {response.status} - {error_text}")

                    result = await response.json()
                    return {
                        "folder_id": folder_id,
                        "files": result.get("files", []),
                        "next_page_token": result.get("nextPageToken"),
                        "count": len(result.get("files", []))
                    }
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to connect to Google Drive API: {str(e)}")


class GoogleDriveReadFileTool(MindscapeTool):
    """Read file content from Google Drive"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com/drive/v3"

        metadata = ToolMetadata(
            name="google_drive_read_file",
            description="Read file content from Google Drive by file ID",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_id": {
                        "type": "string",
                        "description": "Google Drive file ID"
                    },
                    "export_format": {
                        "type": "string",
                        "description": "Export format for Google Docs/Sheets/Slides (e.g., 'text/plain', 'application/pdf')",
                        "enum": ["text/plain", "text/html", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
                    }
                },
                required=["file_id"]
            ),
            category="data",
            source_type="builtin",
            provider="google_drive",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        file_id: str,
        export_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read Google Drive file"""
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                if export_format:
                    url = f"{self.base_url}/files/{file_id}/export"
                    params = {"mimeType": export_format}

                    async with session.get(url, params=params, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise ValueError(f"Google Drive API error: {response.status} - {error_text}")

                        content = await response.read()
                        return {
                            "file_id": file_id,
                            "content": content.decode("utf-8", errors="ignore"),
                            "format": export_format,
                            "size": len(content)
                        }
                else:
                    url = f"{self.base_url}/files/{file_id}"
                    params = {"alt": "media"}

                    async with session.get(url, params=params, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise ValueError(f"Google Drive API error: {response.status} - {error_text}")

                        content = await response.read()

                        metadata_url = f"{self.base_url}/files/{file_id}"
                        metadata_params = {"fields": "id, name, mimeType, size, modifiedTime, webViewLink"}

                        async with session.get(metadata_url, params=metadata_params, headers=headers) as metadata_response:
                            metadata = await metadata_response.json() if metadata_response.status == 200 else {}

                        return {
                            "file_id": file_id,
                            "name": metadata.get("name", ""),
                            "mime_type": metadata.get("mimeType", ""),
                            "content": content.decode("utf-8", errors="ignore"),
                            "size": len(content),
                            "web_view_link": metadata.get("webViewLink")
                        }
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to connect to Google Drive API: {str(e)}")
