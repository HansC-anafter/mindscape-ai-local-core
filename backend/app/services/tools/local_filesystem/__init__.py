"""
Local Filesystem Tools Package
"""
from backend.app.services.tools.local_filesystem.filesystem_tools import (
    FilesystemListFilesTool,
    FilesystemReadFileTool,
    FilesystemWriteFileTool,
    FilesystemSearchTool
)

# Auto-register tools when module is imported
def _auto_register():
    """Auto-register filesystem tools when module is imported."""
    from backend.app.services.tools.registry import register_filesystem_tools
    register_filesystem_tools()

_auto_register()

__all__ = [
    "FilesystemListFilesTool",
    "FilesystemReadFileTool",
    "FilesystemWriteFileTool",
    "FilesystemSearchTool"
]
