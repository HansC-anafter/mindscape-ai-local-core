"""
Obsidian Tools

Tools for interacting with local Obsidian vaults.
Enables reading from and writing to Obsidian notes for research workflows.

Security:
- Only allows access to configured vault paths
- Validates paths to prevent directory traversal
- Respects Obsidian vault structure
"""

from backend.app.services.tools.obsidian_tools import (
    ObsidianListNotesTool,
    ObsidianReadNoteTool,
    ObsidianWriteNoteTool,
    ObsidianAppendNoteTool,
)

__all__ = [
    "ObsidianListNotesTool",
    "ObsidianReadNoteTool",
    "ObsidianWriteNoteTool",
    "ObsidianAppendNoteTool",
]




