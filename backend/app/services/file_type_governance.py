"""
File Type Governance Service

Controls which file types AI can read/write based on extension.
Supports global defaults + workspace-level overrides.

Priority logic:
  effective_allowed = global_allowed ∩ workspace_allowed  (intersection — workspace can only tighten)
  effective_blocked = global_blocked ∪ workspace_blocked  (union — workspace can add more blocks)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_BLOCKED_EXTENSIONS: Set[str] = {
    # Executables
    ".exe",
    ".app",
    ".sh",
    ".bat",
    ".cmd",
    ".com",
    # Installers / packages
    ".msi",
    ".dmg",
    ".pkg",
    ".deb",
    ".rpm",
    ".snap",
    # Libraries / binaries
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".o",
    ".a",
    # Scripts that execute on open
    ".vbs",
    ".ps1",
    ".wsf",
    ".scr",
    # Disk images
    ".iso",
    ".img",
    # Archives (can contain executables)
    ".jar",
    ".war",
}

DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    # Text / Documents
    ".txt",
    ".md",
    ".rtf",
    ".org",
    # Code
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".vue",
    ".svelte",
    ".rs",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    # Config
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".env",
    ".editorconfig",
    ".gitignore",
    ".dockerignore",
    # Web
    ".html",
    ".css",
    ".scss",
    ".less",
    ".svg",
    # Data
    ".csv",
    ".tsv",
    ".xml",
    ".sql",
    # Docs
    ".log",
    ".rst",
    # Shell (read-only category)
    ".zshrc",
    ".bashrc",
    ".bash_profile",
}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

CONFIG_DIR = os.getenv(
    "LOCAL_CONTENT_CONFIG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data"),
)
GLOBAL_CONFIG_FILE = os.path.join(CONFIG_DIR, "file_type_governance.json")


def _load_global_config() -> Dict[str, Any]:
    try:
        if os.path.exists(GLOBAL_CONFIG_FILE):
            with open(GLOBAL_CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load file type governance config: {e}")
    return {}


def _save_global_config(config: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(GLOBAL_CONFIG_FILE), exist_ok=True)
        with open(GLOBAL_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save file type governance config: {e}")


def _load_workspace_config(workspace_id: str) -> Dict[str, Any]:
    ws_file = os.path.join(CONFIG_DIR, f"file_type_governance_{workspace_id}.json")
    try:
        if os.path.exists(ws_file):
            with open(ws_file, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load workspace file type config: {e}")
    return {}


def _save_workspace_config(workspace_id: str, config: Dict[str, Any]) -> None:
    ws_file = os.path.join(CONFIG_DIR, f"file_type_governance_{workspace_id}.json")
    try:
        os.makedirs(os.path.dirname(ws_file), exist_ok=True)
        with open(ws_file, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save workspace file type config: {e}")


# ---------------------------------------------------------------------------
# Core Service
# ---------------------------------------------------------------------------


class FileTypeGovernance:
    """
    File type access governance with global + workspace override.

    Usage:
        gov = FileTypeGovernance()
        if gov.is_allowed("/path/to/file.py"):
            # safe to read
        if gov.is_allowed("/path/to/file.exe"):
            # blocked!
    """

    def is_allowed(
        self,
        file_path: str,
        workspace_id: Optional[str] = None,
    ) -> bool:
        """
        Check if a file is allowed based on its extension.

        Args:
            file_path: Full file path or just filename
            workspace_id: Optional workspace ID for override lookup

        Returns:
            True if the file type is allowed
        """
        ext = Path(file_path).suffix.lower()

        if not ext:
            # No extension — block by default (could be a binary)
            return False

        effective = self.get_effective_config(workspace_id)
        blocked = set(effective["blocked_extensions"])
        allowed = set(effective["allowed_extensions"])

        # Blocked always wins
        if ext in blocked:
            return False

        # Must be in allowed list
        return ext in allowed

    def get_reason(
        self,
        file_path: str,
        workspace_id: Optional[str] = None,
    ) -> str:
        """Return human-readable reason for allow/deny."""
        ext = Path(file_path).suffix.lower()

        if not ext:
            return "No file extension — blocked for safety"

        effective = self.get_effective_config(workspace_id)
        blocked = set(effective["blocked_extensions"])
        allowed = set(effective["allowed_extensions"])

        if ext in blocked:
            return f"Extension '{ext}' is in blocked list (potentially dangerous)"
        if ext not in allowed:
            return f"Extension '{ext}' is not in allowed list"
        return f"Extension '{ext}' is allowed"

    def get_effective_config(
        self,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get merged config: global ∩ workspace_allowed, global ∪ workspace_blocked.
        """
        global_cfg = _load_global_config()
        global_allowed = set(
            global_cfg.get("allowed_extensions", list(DEFAULT_ALLOWED_EXTENSIONS))
        )
        global_blocked = set(
            global_cfg.get("blocked_extensions", list(DEFAULT_BLOCKED_EXTENSIONS))
        )

        if not workspace_id:
            return {
                "allowed_extensions": sorted(global_allowed),
                "blocked_extensions": sorted(global_blocked),
                "source": "global",
            }

        ws_cfg = _load_workspace_config(workspace_id)
        if not ws_cfg:
            return {
                "allowed_extensions": sorted(global_allowed),
                "blocked_extensions": sorted(global_blocked),
                "source": "global",
            }

        # Workspace can only TIGHTEN allowed (intersection)
        ws_allowed = set(ws_cfg.get("allowed_extensions", []))
        if ws_allowed:
            effective_allowed = global_allowed & ws_allowed
        else:
            effective_allowed = global_allowed

        # Workspace can ADD more blocks (union)
        ws_blocked = set(ws_cfg.get("blocked_extensions", []))
        effective_blocked = global_blocked | ws_blocked

        return {
            "allowed_extensions": sorted(effective_allowed),
            "blocked_extensions": sorted(effective_blocked),
            "source": "workspace_override",
        }

    def update_global_config(
        self,
        allowed_extensions: Optional[list] = None,
        blocked_extensions: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Update global file type governance config."""
        config = _load_global_config()
        if allowed_extensions is not None:
            config["allowed_extensions"] = sorted(set(allowed_extensions))
        if blocked_extensions is not None:
            config["blocked_extensions"] = sorted(set(blocked_extensions))
        _save_global_config(config)
        return config

    def update_workspace_config(
        self,
        workspace_id: str,
        allowed_extensions: Optional[list] = None,
        blocked_extensions: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Update workspace-level override config."""
        config = _load_workspace_config(workspace_id)
        if allowed_extensions is not None:
            config["allowed_extensions"] = sorted(set(allowed_extensions))
        if blocked_extensions is not None:
            config["blocked_extensions"] = sorted(set(blocked_extensions))
        _save_workspace_config(workspace_id, config)
        return config


# Singleton
_instance: Optional[FileTypeGovernance] = None


def get_file_type_governance() -> FileTypeGovernance:
    """Get singleton FileTypeGovernance instance."""
    global _instance
    if _instance is None:
        _instance = FileTypeGovernance()
    return _instance
