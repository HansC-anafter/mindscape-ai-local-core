"""
Pack Info Collector

Collects complete information about installed packs from database and registry.
Used for generating dynamic pack lists in LLM prompts.
"""

import logging
from typing import List, Dict, Any, Optional

from backend.app.services.capability_registry import get_registry
from backend.app.services.stores.installed_packs_store import InstalledPacksStore

logger = logging.getLogger(__name__)


class PackInfoCollector:
    """Collects pack information from database and registry for LLM prompt generation"""

    def __init__(self, db_path: str):
        """
        Initialize PackInfoCollector

        Args:
            db_path: Legacy SQLite path (ignored; PostgreSQL is used)
        """
        self.db_path = db_path
        self.store = InstalledPacksStore()

    def get_all_installed_packs(
        self, workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all installed packs with complete information

        Args:
            workspace_id: Optional workspace ID for workspace-specific packs

        Returns:
            List of pack dictionaries containing pack_id, manifest, metadata, etc.
        """
        installed_packs = []

        try:
            rows = self.store.list_installed_metadata()
            registry = get_registry()

            for row in rows:
                pack_id = row.get("pack_id")
                metadata = row.get("metadata") or {}

                capability_info = registry.capabilities.get(pack_id)
                if not capability_info:
                    logger.debug(f"Pack {pack_id} not found in registry, skipping")
                    continue

                manifest = capability_info.get("manifest", {})

                # Load agent_guide content from docs directory
                agent_guide_content = ""
                guide_ref = manifest.get("agent_guide")
                if guide_ref:
                    directory = capability_info.get("directory")
                    if directory:
                        # Path traversal guard
                        guide_path = (directory / guide_ref).resolve()
                        dir_resolved = directory.resolve()
                        if not guide_path.is_relative_to(dir_resolved):
                            logger.warning(
                                "Blocked path traversal in agent_guide for %s: %s",
                                pack_id,
                                guide_ref,
                            )
                        elif guide_path.exists():
                            try:
                                agent_guide_content = guide_path.read_text(
                                    encoding="utf-8"
                                ).strip()[:500]
                            except Exception as e:
                                logger.debug(
                                    f"Failed to read agent_guide for {pack_id}: {e}"
                                )

                installed_packs.append(
                    {
                        "pack_id": pack_id,
                        "display_name": manifest.get("display_name", pack_id),
                        "description": manifest.get("description", ""),
                        "side_effect_level": metadata.get("side_effect_level")
                        or manifest.get("side_effect_level", "readonly"),
                        "manifest": manifest,
                        "metadata": metadata,
                        "agent_guide": agent_guide_content,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to get installed packs: {e}", exc_info=True)

        logger.info(f"Found {len(installed_packs)} installed packs")
        return installed_packs

    def build_pack_description_list(self, packs: List[Dict[str, Any]]) -> str:
        """
        Build formatted pack description list for LLM prompt

        Args:
            packs: List of pack dictionaries from get_all_installed_packs()

        Returns:
            Formatted string listing all packs with descriptions and side_effect_level
        """
        if not packs:
            return "No packs available"

        descriptions = []
        for pack in packs:
            pack_id = pack.get("pack_id", "")
            display_name = pack.get("display_name", pack_id)
            description = pack.get("description", "")
            side_effect = pack.get("side_effect_level", "readonly")

            # Add use cases for better LLM understanding
            use_cases = self._get_pack_use_cases(pack_id)
            use_cases_str = f"Use cases: {', '.join(use_cases)}" if use_cases else ""
            agent_guide = pack.get("agent_guide", "")

            desc_line = (
                f"- {pack_id} ({display_name}): {description} [{side_effect}]\n"
                f"  {use_cases_str}"
            )
            if agent_guide:
                desc_line += f"\n  [Agent Guide] {agent_guide}"
            descriptions.append(desc_line)

        return "\n".join(descriptions)

    def _get_pack_use_cases(self, pack_id: str) -> List[str]:
        """
        Get use cases for a pack to help LLM understand when to use it.

        DEPRECATED: Hardcoded use_cases have been removed.
        This method now returns an empty list.
        Use SKILL.md + RAG pipeline for dynamic skill discovery.

        Args:
            pack_id: Pack identifier

        Returns:
            Empty list (hardcoded data removed)
        """
        return []
