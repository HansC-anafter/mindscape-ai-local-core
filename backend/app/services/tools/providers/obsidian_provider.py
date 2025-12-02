"""
Obsidian Tool Discovery Provider

Discovers Obsidian vault capabilities for local vault access.
Enables reading from and writing to Obsidian notes for research workflows.

Security:
- Only allows access to configured vault paths
- Validates vault structure
- Prevents directory traversal attacks
"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.app.services.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)
from backend.app.services.obsidian.obsidian_tools import (
    ObsidianListNotesTool,
    ObsidianReadNoteTool,
    ObsidianWriteNoteTool,
    ObsidianAppendNoteTool,
)

logger = logging.getLogger(__name__)


class ObsidianDiscoveryProvider(ToolDiscoveryProvider):
    """
    Obsidian Discovery Provider

    Discovers Obsidian vault capabilities for configured vaults.
    """

    @property
    def provider_name(self) -> str:
        return "obsidian"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["local"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Obsidian vault capabilities

        Returns tools for:
        - Listing notes in vault
        - Reading notes
        - Writing notes
        - Appending to notes
        """
        vault_paths = config.custom_config.get("vault_paths", [])
        include_folders = config.custom_config.get("include_folders", [])
        exclude_folders = config.custom_config.get("exclude_folders", [".obsidian", "Templates"])

        if not vault_paths:
            logger.warning("No vault paths configured for Obsidian")
            return []

        discovered_tools = []

        for vault_path in vault_paths:
            vault = Path(vault_path).expanduser().resolve()

            if not self._is_valid_vault(vault):
                logger.warning(f"Invalid or inaccessible vault: {vault_path}")
                continue

            base_tool_id = f"obsidian_{vault.name}"

            discovered_tools.extend([
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_list",
                    display_name=f"List Notes: {vault.name}",
                    description=f"List notes in Obsidian vault at {vault}",
                    category="data",
                    endpoint=str(vault),
                    methods=["GET"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "folder": {
                                "type": "string",
                                "description": "Filter by folder path"
                            },
                            "tag": {
                                "type": "string",
                                "description": "Filter by tag"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of notes",
                                "default": 50
                            }
                        },
                        "required": []
                    },
                    danger_level="low",
                    metadata={
                        "vault_path": str(vault),
                        "include_folders": include_folders,
                        "exclude_folders": exclude_folders
                    }
                ),
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_read",
                    display_name=f"Read Note: {vault.name}",
                    description=f"Read note content from Obsidian vault at {vault}",
                    category="data",
                    endpoint=str(vault),
                    methods=["GET"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "note_path": {
                                "type": "string",
                                "description": "Relative path to note file"
                            }
                        },
                        "required": ["note_path"]
                    },
                    danger_level="low",
                    metadata={
                        "vault_path": str(vault)
                    }
                ),
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_write",
                    display_name=f"Write Note: {vault.name}",
                    description=f"Write or overwrite note in Obsidian vault at {vault}",
                    category="content",
                    endpoint=str(vault),
                    methods=["POST"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "note_path": {
                                "type": "string",
                                "description": "Relative path to note file"
                            },
                            "title": {
                                "type": "string",
                                "description": "Note title"
                            },
                            "body": {
                                "type": "string",
                                "description": "Note content in markdown"
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tags to add"
                            },
                            "frontmatter": {
                                "type": "object",
                                "description": "Additional frontmatter fields"
                            }
                        },
                        "required": ["note_path", "body"]
                    },
                    danger_level="medium",
                    metadata={
                        "vault_path": str(vault)
                    }
                ),
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_append",
                    display_name=f"Append Note: {vault.name}",
                    description=f"Append content to note in Obsidian vault at {vault}",
                    category="content",
                    endpoint=str(vault),
                    methods=["POST"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "note_path": {
                                "type": "string",
                                "description": "Relative path to note file"
                            },
                            "body": {
                                "type": "string",
                                "description": "Content to append"
                            },
                            "section_title": {
                                "type": "string",
                                "description": "Optional section title"
                            }
                        },
                        "required": ["note_path", "body"]
                    },
                    danger_level="medium",
                    metadata={
                        "vault_path": str(vault)
                    }
                )
            ])

        logger.info(f"Discovered {len(discovered_tools)} Obsidian tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Obsidian configuration

        Checks:
        - At least one vault path is configured
        - All vault paths exist and are accessible
        - All vaults have .obsidian folder (valid Obsidian vault)
        """
        vault_paths = config.custom_config.get("vault_paths", [])

        if not vault_paths:
            logger.error("No vault paths configured")
            return False

        for vault_path in vault_paths:
            vault = Path(vault_path).expanduser().resolve()

            if not self._is_valid_vault(vault):
                return False

        return True

    def _is_valid_vault(self, vault: Path) -> bool:
        """Check if path is a valid Obsidian vault"""
        if not vault.exists():
            logger.error(f"Vault path does not exist: {vault}")
            return False

        if not vault.is_dir():
            logger.error(f"Vault path is not a directory: {vault}")
            return False

        if not os.access(vault, os.R_OK):
            logger.error(f"Vault is not readable: {vault}")
            return False

        obsidian_config = vault / ".obsidian"
        if not obsidian_config.exists():
            logger.warning(f"Path may not be an Obsidian vault (no .obsidian folder): {vault}")
            return True

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "description": "Obsidian vault access for research workflows and knowledge management",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["vault_paths"],
            "optional_config": ["include_folders", "exclude_folders"],
            "documentation_url": None,
            "security_notes": [
                "Only configured vault paths are accessible",
                "Directory traversal attacks are prevented",
                "Write access requires explicit configuration"
            ]
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": self.provider_name
                },
                "connection_type": {
                    "type": "string",
                    "enum": self.supported_connection_types
                },
                "vault_paths": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of Obsidian vault paths",
                    "minItems": 1
                },
                "include_folders": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Folders to include (e.g., ['Research/', 'Projects/'])",
                    "default": []
                },
                "exclude_folders": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "Folders to exclude (e.g., ['.obsidian', 'Templates'])",
                    "default": [".obsidian", "Templates"]
                }
            },
            "required": ["tool_type", "connection_type", "vault_paths"]
        }

    def create_tool_instance(self, tool_id: str, metadata: Dict[str, Any]) -> Optional[Any]:
        """
        Create tool instance from discovered tool metadata

        This is called by the tool registry to instantiate tools.
        """
        vault_path = metadata.get("vault_path")
        if not vault_path:
            return None

        include_folders = metadata.get("include_folders", [])
        exclude_folders = metadata.get("exclude_folders", [".obsidian", "Templates"])

        if tool_id.endswith("_list"):
            return ObsidianListNotesTool(vault_path, include_folders, exclude_folders)
        elif tool_id.endswith("_read"):
            return ObsidianReadNoteTool(vault_path)
        elif tool_id.endswith("_write"):
            return ObsidianWriteNoteTool(vault_path)
        elif tool_id.endswith("_append"):
            return ObsidianAppendNoteTool(vault_path)

        return None




