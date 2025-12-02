"""
Local Filesystem Tools

Tools for accessing local file system.
Used for document collection and RAG functionality.

Security:
- Only allows access to configured directories
- Validates paths to prevent directory traversal
"""
import os
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class FilesystemListFilesTool(MindscapeTool):
    """List files and directories"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="filesystem_list_files",
            description=f"List files and directories in {self.base_directory}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "path": {
                        "type": "string",
                        "description": f"Relative path from {self.base_directory}",
                        "default": "."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List recursively",
                        "default": False
                    }
                },
                required=[]
            ),
            category="file_management",
            source_type="builtin",
            provider="local_filesystem",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self, path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        """List files in directory"""
        target_path = self._validate_path(path)

        if not target_path.exists():
            raise ValueError(f"Path does not exist: {path}")

        if not target_path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        files = []
        directories = []

        if recursive:
            for root, dirs, filenames in os.walk(target_path):
                rel_root = os.path.relpath(root, self.base_directory)
                for dirname in dirs:
                    directories.append(os.path.join(rel_root, dirname).replace("\\", "/"))
                for filename in filenames:
                    files.append(os.path.join(rel_root, filename).replace("\\", "/"))
        else:
            for item in target_path.iterdir():
                item_path = item.relative_to(self.base_directory)
                if item.is_dir():
                    directories.append(str(item_path).replace("\\", "/"))
                else:
                    files.append(str(item_path).replace("\\", "/"))

        return {
            "path": path,
            "files": sorted(files),
            "directories": sorted(directories),
            "count": len(files) + len(directories)
        }

    def _validate_path(self, relative_path: str) -> Path:
        """Validate and resolve path"""
        target = (self.base_directory / relative_path).resolve()

        if not str(target).startswith(str(self.base_directory)):
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target


class FilesystemReadFileTool(MindscapeTool):
    """Read file content"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="filesystem_read_file",
            description=f"Read file content from {self.base_directory}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_path": {
                        "type": "string",
                        "description": f"Relative file path from {self.base_directory}"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding",
                        "default": "utf-8"
                    }
                },
                required=["file_path"]
            ),
            category="file_management",
            source_type="builtin",
            provider="local_filesystem",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read file content"""
        target_file = self._validate_path(file_path)

        if not target_file.exists():
            raise ValueError(f"File does not exist: {file_path}")

        if not target_file.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        try:
            with open(target_file, "r", encoding=encoding) as f:
                content = f.read()

            return {
                "file_path": file_path,
                "content": content,
                "size": target_file.stat().st_size,
                "encoding": encoding
            }
        except UnicodeDecodeError:
            raise ValueError(f"Cannot decode file with encoding {encoding}. Try 'latin-1' or 'binary'")
        except Exception as e:
            raise ValueError(f"Error reading file: {str(e)}")

    def _validate_path(self, relative_path: str) -> Path:
        """Validate and resolve path"""
        target = (self.base_directory / relative_path).resolve()

        if not str(target).startswith(str(self.base_directory)):
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target


class FilesystemWriteFileTool(MindscapeTool):
    """Write file content"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="filesystem_write_file",
            description=f"Write file content to {self.base_directory}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_path": {
                        "type": "string",
                        "description": f"Relative file path from {self.base_directory}"
                    },
                    "content": {
                        "type": "string",
                        "description": "File content to write"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding",
                        "default": "utf-8"
                    }
                },
                required=["file_path", "content"]
            ),
            category="file_management",
            source_type="builtin",
            provider="local_filesystem",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(self, file_path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Write file content"""
        target_file = self._validate_path(file_path)

        target_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(target_file, "w", encoding=encoding) as f:
                f.write(content)

            return {
                "file_path": file_path,
                "size": len(content.encode(encoding)),
                "encoding": encoding,
                "success": True
            }
        except Exception as e:
            raise ValueError(f"Error writing file: {str(e)}")

    def _validate_path(self, relative_path: str) -> Path:
        """Validate and resolve path"""
        target = (self.base_directory / relative_path).resolve()

        if not str(target).startswith(str(self.base_directory)):
            raise ValueError(f"Path traversal detected: {relative_path}")

        return target


class FilesystemSearchTool(MindscapeTool):
    """Search files by name or content"""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory).expanduser().resolve()

        metadata = ToolMetadata(
            name="filesystem_search",
            description=f"Search files by name or content in {self.base_directory}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "query": {
                        "type": "string",
                        "description": "Search query (filename pattern or content)"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern (e.g., '*.md', '*.txt')",
                        "default": "*"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search recursively",
                        "default": True
                    }
                },
                required=["query"]
            ),
            category="file_management",
            source_type="builtin",
            provider="local_filesystem",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        query: str,
        file_pattern: str = "*",
        recursive: bool = True
    ) -> Dict[str, Any]:
        """Search files"""
        matches = []

        if recursive:
            for root, dirs, filenames in os.walk(self.base_directory):
                for filename in filenames:
                    if fnmatch.fnmatch(filename, file_pattern):
                        file_path = Path(root) / filename
                        rel_path = file_path.relative_to(self.base_directory)

                        if query.lower() in filename.lower():
                            matches.append({
                                "file_path": str(rel_path).replace("\\", "/"),
                                "match_type": "filename"
                            })
                        else:
                            try:
                                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                    if query.lower() in content.lower():
                                        matches.append({
                                            "file_path": str(rel_path).replace("\\", "/"),
                                            "match_type": "content"
                                        })
                            except Exception:
                                pass
        else:
            for item in self.base_directory.iterdir():
                if item.is_file() and fnmatch.fnmatch(item.name, file_pattern):
                    if query.lower() in item.name.lower():
                        matches.append({
                            "file_path": item.name,
                            "match_type": "filename"
                        })

        return {
            "query": query,
            "file_pattern": file_pattern,
            "matches": matches,
            "count": len(matches)
        }
