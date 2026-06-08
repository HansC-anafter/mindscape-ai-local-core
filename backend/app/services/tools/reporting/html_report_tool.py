"""Builtin workspace HTML report writer."""

from __future__ import annotations

import html as html_escape
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)


DEFAULT_REPORT_SUBDIR = "reports/html"
MAX_HTML_BYTES = 2 * 1024 * 1024
_SAFE_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_BLOCKED_HTML_MARKERS = ("<script", "javascript:")


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_file_name(file_name: str) -> str:
    value = file_name.strip()
    if not value:
        raise ValueError("file_name is required")
    if value != PurePosixPath(value).name or "\\" in value:
        raise ValueError("file_name must be a single file name")
    if not value.lower().endswith(".html"):
        raise ValueError("file_name must end with .html")
    return value


def _validate_relative_subdir(report_subdir: Optional[str]) -> PurePosixPath:
    value = (report_subdir or DEFAULT_REPORT_SUBDIR).strip().strip("/")
    if not value:
        value = DEFAULT_REPORT_SUBDIR
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("report_subdir must be a safe relative path")
    return path


def _validate_workspace_id(workspace_id: Optional[str]) -> Optional[str]:
    if workspace_id is None:
        return None
    value = workspace_id.strip()
    if not value or not _SAFE_WORKSPACE_ID_RE.match(value):
        raise ValueError("workspace_id contains unsupported characters")
    return value


def _normalize_html(title: Optional[str], content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("html content is required")

    lowered = content.lower()
    if any(marker in lowered for marker in _BLOCKED_HTML_MARKERS):
        raise ValueError("html content must be static and must not include scripts")

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_HTML_BYTES:
        raise ValueError("html content exceeds the 2 MiB limit")

    stripped = content.lstrip()
    lowered_stripped = stripped.lower()
    if lowered_stripped.startswith("<!doctype html"):
        return content
    if lowered_stripped.startswith("<html"):
        return "<!doctype html>\n" + content

    safe_title = html_escape.escape(title or "Workspace Report", quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="zh-TW">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{safe_title}</title>\n"
        "</head>\n"
        "<body>\n"
        f"{content}\n"
        "</body>\n"
        "</html>\n"
    )


class WorkspaceHtmlReportTool(MindscapeTool):
    """Write a static HTML report into a workspace sandbox."""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_write_html_report",
            description=(
                "Write a static .html report artifact into a workspace sandbox "
                "report directory for Meeting Engine and capability pack outputs."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_name": {
                        "type": "string",
                        "description": "Single .html file name to create",
                    },
                    "html": {
                        "type": "string",
                        "description": "Static HTML document or body fragment",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Workspace identifier. Used with DATA_DIR/workspaces "
                            "when sandbox_path is not provided."
                        ),
                    },
                    "sandbox_path": {
                        "type": "string",
                        "description": (
                            "Absolute sandbox root under DATA_DIR/workspaces. "
                            "Used by workspace-bound runtimes."
                        ),
                    },
                    "report_subdir": {
                        "type": "string",
                        "description": "Safe relative output directory inside sandbox",
                        "default": DEFAULT_REPORT_SUBDIR,
                    },
                    "title": {
                        "type": "string",
                        "description": "Report title used when wrapping fragments",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite an existing report file",
                        "default": False,
                    },
                },
                required=["file_name", "html"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace_reporting",
            danger_level="medium",
            tags=["meeting_engine", "reporting", "html", "workspace"],
        )
        super().__init__(metadata)

    async def execute(
        self,
        file_name: str,
        html: str,
        workspace_id: Optional[str] = None,
        sandbox_path: Optional[str] = None,
        report_subdir: Optional[str] = DEFAULT_REPORT_SUBDIR,
        title: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Write a static HTML report into a workspace sandbox."""
        safe_workspace_id = _validate_workspace_id(workspace_id)
        safe_file_name = _validate_file_name(file_name)
        safe_subdir = _validate_relative_subdir(report_subdir)
        normalized_html = _normalize_html(title, html)

        data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        workspaces_root = (data_dir / "workspaces").resolve()

        if sandbox_path:
            sandbox_root = Path(sandbox_path).expanduser().resolve()
        elif safe_workspace_id:
            sandbox_root = (workspaces_root / safe_workspace_id / "sandbox").resolve()
        else:
            raise ValueError("workspace_id or sandbox_path is required")

        if not _is_relative_to(sandbox_root, workspaces_root):
            raise ValueError("sandbox_path must be under DATA_DIR/workspaces")
        if safe_workspace_id:
            workspace_root = (workspaces_root / safe_workspace_id).resolve()
            if not _is_relative_to(sandbox_root, workspace_root):
                raise ValueError("sandbox_path must belong to workspace_id")

        target_dir = sandbox_root.joinpath(*safe_subdir.parts).resolve()
        target_path = (target_dir / safe_file_name).resolve()
        if not _is_relative_to(target_path, sandbox_root):
            raise ValueError("target path must remain under sandbox root")

        file_existed = target_path.exists()
        if file_existed and not overwrite:
            raise ValueError("report file already exists and overwrite is false")

        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(normalized_html, encoding="utf-8")
        size = target_path.stat().st_size

        return {
            "success": True,
            "artifact_kind": "html_report",
            "content_type": "text/html; charset=utf-8",
            "workspace_id": safe_workspace_id,
            "sandbox_path": str(sandbox_root),
            "relative_path": str(PurePosixPath(*safe_subdir.parts) / safe_file_name),
            "file_path": str(target_path),
            "size": size,
            "title": title,
            "file_existed": file_existed,
            "overwrite": overwrite,
        }
