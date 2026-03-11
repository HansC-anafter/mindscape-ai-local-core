"""
Device Node Apple Notes Service

Reads Apple Notes via Device Node's shell_execute + osascript.
Follows the same MCP HTTP pattern as device_node_filesystem.py.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class DeviceNodeNotesService:
    """
    Reads Apple Notes folders and note content via Device Node.

    Uses shell_execute tool with osascript commands to interact
    with Apple Notes on the host machine.

    Usage:
        notes = get_device_node_notes()
        folders = await notes.list_folders()
        content = await notes.read_note("Notes", "My Note Title")
    """

    def __init__(self):
        self.device_node_url = os.getenv(
            "DEVICE_NODE_URL", "http://host.docker.internal:3100"
        )
        self.timeout = float(os.getenv("DEVICE_NODE_NOTES_TIMEOUT", "30"))

    async def _run_osascript(self, script: str) -> str:
        """
        Execute an AppleScript via Device Node shell_execute.

        Args:
            script: AppleScript code to execute

        Returns:
            stdout output from osascript

        Raises:
            NotesServiceError: On connection or execution errors
        """
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "shell_execute",
                "arguments": {
                    "command": "osascript",
                    "args": ["-e", script],
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mindscape-LocalCore/1.0",
            "X-Request-Source": "notes-service",
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
                raise NotesServiceError(f"osascript error: {error_msg}")

            content_list = result.get("result", {}).get("content", [])
            if content_list:
                return content_list[0].get("text", "")
            return ""

        except httpx.ConnectError:
            raise NotesServiceError(
                "Device Node not reachable. "
                "Start it on host with: cd device-node && npm run dev"
            )
        except httpx.TimeoutException:
            raise NotesServiceError(f"Device Node timeout after {self.timeout}s")
        except NotesServiceError:
            raise
        except Exception as e:
            raise NotesServiceError(f"Notes service call failed: {e}")

    async def is_available(self) -> bool:
        """Check if Apple Notes is accessible via Device Node."""
        try:
            result = await self._run_osascript(
                'tell application "Notes" to return "ok"'
            )
            return result.strip() == "ok"
        except Exception:
            return False

    async def list_folders(self) -> List[str]:
        """
        List all Apple Notes folders.

        Returns:
            List of folder names (e.g. ["Notes", "Work", "Personal"])
        """
        script = 'tell application "Notes" to get name of every folder'
        result = await self._run_osascript(script)

        if not result.strip():
            return []

        # osascript returns comma-separated list
        folders = [f.strip() for f in result.split(",") if f.strip()]
        return folders

    async def list_notes(self, folder: str) -> List[Dict[str, Any]]:
        """
        List notes in a specific folder.

        Args:
            folder: Folder name

        Returns:
            List of dicts with keys: name, id, creation_date, modification_date
        """
        # Escape quotes in folder name
        safe_folder = folder.replace('"', '\\"')

        script = f"""
tell application "Notes"
    set noteList to ""
    set theNotes to every note of folder "{safe_folder}"
    repeat with theNote in theNotes
        set noteName to name of theNote
        set noteId to id of theNote
        set noteList to noteList & noteName & "|||" & noteId & "\\n"
    end repeat
    return noteList
end tell
"""
        result = await self._run_osascript(script)

        notes = []
        for line in result.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) >= 2:
                notes.append(
                    {
                        "name": parts[0].strip(),
                        "id": parts[1].strip(),
                    }
                )
            elif parts:
                notes.append({"name": parts[0].strip(), "id": ""})

        return notes

    async def read_note(self, folder: str, note_name: str) -> str:
        """
        Read the plain text body of a note.

        Args:
            folder: Folder name
            note_name: Note title

        Returns:
            Plain text content of the note
        """
        safe_folder = folder.replace('"', '\\"')
        safe_name = note_name.replace('"', '\\"')

        script = f"""
tell application "Notes"
    set theNote to first note of folder "{safe_folder}" whose name is "{safe_name}"
    return plaintext of theNote
end tell
"""
        return await self._run_osascript(script)


class NotesServiceError(Exception):
    """Raised when Apple Notes service communication fails."""

    pass


# Singleton
_service: Optional[DeviceNodeNotesService] = None


def get_device_node_notes() -> DeviceNodeNotesService:
    """Get singleton DeviceNodeNotesService instance."""
    global _service
    if _service is None:
        _service = DeviceNodeNotesService()
    return _service
