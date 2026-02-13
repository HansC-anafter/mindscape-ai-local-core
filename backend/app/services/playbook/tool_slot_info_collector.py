"""
Tool Slot Info Collector

Collects tool slot information from playbook.json and workspace mappings
for injection into LLM prompts in Conversation mode.
"""

import logging
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

from backend.app.models.playbook import ToolPolicy

logger = logging.getLogger(__name__)


@dataclass
class ToolSlotInfo:
    """
    Tool slot information for LLM prompt injection
    """

    slot: str  # e.g., "cms.footer.apply_style"
    description: Optional[str] = (
        None  # From playbook.json step metadata.description or mapping metadata.description
    )
    policy: Optional[ToolPolicy] = None  # Policy constraints
    mapped_tool_id: Optional[str] = None  # Current mapped tool_id (if configured)
    mapped_tool_description: Optional[str] = None  # Tool description (optional)
    source: str = "unknown"  # "playbook" or "workspace" or "project"
    relevance_score: Optional[float] = (
        None  # Relevance score from intent analysis (0.0-1.0)
    )
    tags: Optional[List[str]] = None  # Tags for LLM context (from metadata.tags)
    priority: int = (
        0  # Priority (0-100) for sorting: playbook_defined > recently_used > workspace_common > generic
    )


class ToolSlotInfoCollector:
    """
    Collects tool slot information for LLM prompts

    Sources:
    1. Playbook.json steps (priority) - extracts tool_slot and tool_policy
    2. Workspace/Project mappings - shows available slot mappings
    """

    def __init__(self, store=None):
        """
        Initialize collector

        Args:
            store: MindscapeStore instance (optional)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
        self.store = store

    async def collect_slot_info(
        self,
        playbook_code: str,
        workspace_id: str,
        project_id: Optional[str] = None,
        user_message: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        enable_intent_filtering: bool = True,
        capability_profile: Optional[str] = None,
        stage_router: Optional[Any] = None,
        llm_provider_manager: Optional[Any] = None,
    ) -> Dict[str, ToolSlotInfo]:
        """
        Collect tool slot information for LLM prompt

        Args:
            playbook_code: Playbook code
            workspace_id: Workspace ID
            project_id: Optional project ID
            user_message: User message (for intent filtering)
            conversation_history: Conversation history (for intent filtering)
            enable_intent_filtering: Whether to enable LLM-based intent filtering

        Returns:
            Dict mapping slot -> ToolSlotInfo (filtered and ranked if intent filtering enabled)
        """
        slot_info_map: Dict[str, ToolSlotInfo] = {}

        # Source 1: Extract from playbook.json (priority)
        playbook_slots = await self._extract_from_playbook_json(playbook_code)
        for slot, info in playbook_slots.items():
            slot_info_map[slot] = info
            logger.debug(f"Collected slot from playbook.json: {slot}")

        # Source 2: Collect from workspace/project mappings
        workspace_slots = await self._collect_from_mappings(
            workspace_id=workspace_id,
            project_id=project_id,
            exclude_slots=set(slot_info_map.keys()),  # Don't override playbook slots
        )
        for slot, info in workspace_slots.items():
            slot_info_map[slot] = info
            logger.debug(f"Collected slot from mappings: {slot}")

        # Source 3: Auto-inject installed capability pack tools (with RAG)
        capability_slots, rag_status = await self._collect_from_capabilities(
            exclude_slots=set(slot_info_map.keys()),
            user_message=user_message,
        )
        for slot, info in capability_slots.items():
            slot_info_map[slot] = info
            logger.debug(f"Auto-injected capability tool: {slot}")

        # Resolve mapped tool IDs
        slot_info_map = await self.resolve_mapped_tool_ids(
            slot_info_map=slot_info_map,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        logger.info(
            f"Collected {len(slot_info_map)} tool slots for playbook {playbook_code}"
        )

        # Skip expensive LLM intent filtering when RAG already filtered tools
        if rag_status == "hit" and enable_intent_filtering:
            enable_intent_filtering = False
            logger.info("RAG hit, skipping LLM intent filtering")

        # Intent filtering (if enabled and user message provided)
        if enable_intent_filtering and user_message and len(slot_info_map) > 5:
            try:
                from backend.app.services.playbook.intent_analyzer import (
                    get_tool_slot_intent_analyzer,
                )
                from backend.app.services.config_store import ConfigStore
                from backend.app.services.playbook.llm_provider_manager import (
                    PlaybookLLMProviderManager,
                )
                from backend.app.services.conversation.capability_profile import (
                    CapabilityProfile,
                    CapabilityProfileRegistry,
                )
                from backend.app.services.system_settings_store import (
                    SystemSettingsStore,
                )
                from backend.app.shared.llm_provider_helper import (
                    get_model_name_from_chat_model,
                )

                # Priority: stage_router > capability_profile > SystemSettings > chat_model
                selected_model_name = None
                profile_id = None  # Can be passed from context if available

                # Use stage_router if provided
                if stage_router:
                    try:
                        profile = stage_router.get_profile_for_stage("intent_analysis")
                        registry = CapabilityProfileRegistry()
                        # Get LLMProviderManager from PlaybookLLMProviderManager
                        if not llm_provider_manager:
                            config_store = ConfigStore()
                            llm_provider_manager = PlaybookLLMProviderManager(
                                config_store
                            )
                        llm_manager = llm_provider_manager.get_llm_manager(
                            profile_id or "default-user"
                        )
                        selected_model_name = registry.select_model(
                            profile, llm_manager, profile_id=profile_id
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to use stage_router: {e}, trying next option"
                        )

                # Use capability_profile if provided (and stage_router didn't work)
                if not selected_model_name and capability_profile:
                    try:
                        profile = CapabilityProfile(capability_profile)
                        registry = CapabilityProfileRegistry()
                        if not llm_provider_manager:
                            config_store = ConfigStore()
                            llm_provider_manager = PlaybookLLMProviderManager(
                                config_store
                            )
                        llm_manager = llm_provider_manager.get_llm_manager(
                            profile_id or "default-user"
                        )
                        selected_model_name = registry.select_model(
                            profile, llm_manager, profile_id=profile_id
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to use capability_profile: {e}, trying next option"
                        )

                # Use SystemSettings if available (and previous options didn't work)
                if not selected_model_name:
                    try:
                        settings_store = SystemSettingsStore()
                        mapping = settings_store.get_capability_profile_mapping()
                        profile_name = mapping.get("intent_analysis", "fast")
                        profile = CapabilityProfile(profile_name)
                        registry = CapabilityProfileRegistry()
                        if not llm_provider_manager:
                            config_store = ConfigStore()
                            llm_provider_manager = PlaybookLLMProviderManager(
                                config_store
                            )
                        llm_manager = llm_provider_manager.get_llm_manager(
                            profile_id or "default-user"
                        )
                        selected_model_name = registry.select_model(
                            profile, llm_manager, profile_id=profile_id
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to use SystemSettings: {e}, trying next option"
                        )

                # 4. Fallback to chat_model
                if not selected_model_name:
                    selected_model_name = get_model_name_from_chat_model()
                    logger.debug(f"Using chat_model fallback: {selected_model_name}")

                # Initialize LLM provider manager for intent analysis (if not provided)
                if not llm_provider_manager:
                    config_store = ConfigStore()
                    llm_provider_manager = PlaybookLLMProviderManager(config_store)

                analyzer = get_tool_slot_intent_analyzer(
                    llm_provider_manager=llm_provider_manager,
                    profile_id=profile_id,
                    model_name=selected_model_name,
                )
                tool_list = list(slot_info_map.values())

                filtered_tools = await analyzer.analyze_and_filter_tools(
                    user_message=user_message,
                    available_tools=tool_list,
                    conversation_history=conversation_history,
                    playbook_code=playbook_code,
                    max_tools=10,
                    min_relevance=0.3,
                )

                # Update slot_info_map with filtered tools (maintain relevance scores)
                filtered_slot_info_map = {tool.slot: tool for tool in filtered_tools}

                logger.info(
                    f"Intent filtering: {len(slot_info_map)} -> {len(filtered_slot_info_map)} tools"
                )
                return filtered_slot_info_map

            except Exception as e:
                logger.warning(
                    f"Intent filtering failed: {e}, using all tools", exc_info=True
                )
                # Fallback to all tools
                return slot_info_map

        return slot_info_map

    async def _extract_from_playbook_json(
        self, playbook_code: str
    ) -> Dict[str, ToolSlotInfo]:
        """
        Extract tool slots from playbook.json

        Args:
            playbook_code: Playbook code

        Returns:
            Dict mapping slot -> ToolSlotInfo
        """
        slot_info_map: Dict[str, ToolSlotInfo] = {}

        try:
            from backend.app.services.playbook_loaders.json_loader import (
                PlaybookJsonLoader,
            )

            playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
            if not playbook_json or not playbook_json.steps:
                return slot_info_map

            # Extract tool_slot from each step
            for step in playbook_json.steps:
                if hasattr(step, "tool_slot") and step.tool_slot:
                    slot = step.tool_slot

                    # Extract policy if present
                    policy = None
                    if hasattr(step, "tool_policy") and step.tool_policy:
                        policy = step.tool_policy

                    # Extract description from step metadata (design requirement: description quality is core for filtering)
                    description = None
                    tags = None
                    if hasattr(step, "metadata") and step.metadata:
                        description = (
                            step.metadata.get("description")
                            if isinstance(step.metadata, dict)
                            else None
                        )
                        tags = (
                            step.metadata.get("tags")
                            if isinstance(step.metadata, dict)
                            else None
                        )

                    # Fallback to step.id only if no description available
                    if not description:
                        description = f"Step: {step.id}"
                    else:
                        # Ensure description is meaningful
                        description = str(description).strip()

                    # Extract priority: playbook-defined steps have high priority (80-100)
                    priority = 90  # High priority for playbook-defined slots

                    # Try to resolve slot to tool_id (to show mapping)
                    mapped_tool_id = None
                    try:
                        from backend.app.services.tool_slot_resolver import (
                            get_tool_slot_resolver,
                        )

                        resolver = get_tool_slot_resolver(store=self.store)
                        # We need workspace_id to resolve, but we don't have it here
                        # So we'll resolve later in _resolve_mapped_tool_id
                    except Exception as e:
                        logger.debug(
                            f"Could not resolve slot {slot} in playbook extraction: {e}"
                        )

                    slot_info_map[slot] = ToolSlotInfo(
                        slot=slot,
                        description=description,
                        policy=policy,
                        mapped_tool_id=mapped_tool_id,
                        source="playbook",
                        tags=tags if isinstance(tags, list) else None,
                        priority=priority,
                    )

        except Exception as e:
            logger.warning(
                f"Failed to extract slots from playbook.json for {playbook_code}: {e}"
            )

        return slot_info_map

    async def _collect_from_mappings(
        self,
        workspace_id: str,
        project_id: Optional[str] = None,
        exclude_slots: Optional[set] = None,
    ) -> Dict[str, ToolSlotInfo]:
        """
        Collect tool slots from workspace/project mappings

        Args:
            workspace_id: Workspace ID
            project_id: Optional project ID
            exclude_slots: Slots to exclude (already collected from playbook.json)

        Returns:
            Dict mapping slot -> ToolSlotInfo
        """
        slot_info_map: Dict[str, ToolSlotInfo] = {}
        exclude_slots = exclude_slots or set()

        try:
            from backend.app.services.stores.tool_slot_mappings_store import (
                ToolSlotMappingsStore,
            )

            mappings_store = ToolSlotMappingsStore(self.store.db_path)

            # Get workspace-level mappings
            workspace_mappings = mappings_store.get_mappings(
                workspace_id=workspace_id,
                project_id=None,  # Workspace-level only
                enabled_only=True,
            )

            # Get project-level mappings (if project_id provided)
            project_mappings = []
            if project_id:
                project_mappings = mappings_store.get_mappings(
                    workspace_id=workspace_id, project_id=project_id, enabled_only=True
                )

            # Combine mappings (project-level take priority)
            all_mappings = {m["slot"]: m for m in workspace_mappings}
            for m in project_mappings:
                all_mappings[m["slot"]] = m  # Project mappings override workspace

            # Convert to ToolSlotInfo
            for mapping in all_mappings.values():
                slot = mapping["slot"]
                if slot in exclude_slots:
                    continue  # Skip slots already collected from playbook.json

                # Extract policy from metadata if present
                policy = None
                metadata = mapping.get("metadata", {})
                if metadata:
                    # Try to extract policy from metadata
                    policy_dict = metadata.get("policy")
                    if policy_dict:
                        try:
                            policy = ToolPolicy(**policy_dict)
                        except Exception as e:
                            logger.debug(
                                f"Failed to parse policy from metadata for slot {slot}: {e}"
                            )

                source = "project" if mapping.get("project_id") else "workspace"

                # Extract description, tags, and priority from metadata
                description = metadata.get("description") if metadata else None
                tags = (
                    metadata.get("tags")
                    if metadata and isinstance(metadata.get("tags"), list)
                    else None
                )
                priority = (
                    metadata.get("priority", 50) if metadata else 50
                )  # Default priority for workspace/project mappings

                # Project-level mappings have higher priority than workspace-level
                if source == "project":
                    priority = max(priority, 70)
                else:
                    priority = max(priority, 50)

                slot_info_map[slot] = ToolSlotInfo(
                    slot=slot,
                    description=description,
                    policy=policy,
                    mapped_tool_id=mapping.get("tool_id"),
                    source=source,
                    tags=tags,
                    priority=priority,
                )

        except Exception as e:
            logger.warning(f"Failed to collect slots from mappings: {e}")

        return slot_info_map

    async def resolve_mapped_tool_ids(
        self,
        slot_info_map: Dict[str, ToolSlotInfo],
        workspace_id: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, ToolSlotInfo]:
        """
        Resolve mapped tool IDs for slots that don't have them yet

        Args:
            slot_info_map: Slot info map to update
            workspace_id: Workspace ID
            project_id: Optional project ID

        Returns:
            Updated slot_info_map with resolved tool_ids
        """
        try:
            from backend.app.services.tool_slot_resolver import (
                get_tool_slot_resolver,
                SlotNotFoundError,
            )

            resolver = get_tool_slot_resolver(store=self.store)

            for slot, info in slot_info_map.items():
                if not info.mapped_tool_id:
                    try:
                        tool_id = await resolver.resolve(
                            slot=slot, workspace_id=workspace_id, project_id=project_id
                        )
                        info.mapped_tool_id = tool_id
                        logger.debug(f"Resolved slot {slot} to tool {tool_id}")
                    except SlotNotFoundError:
                        # Slot not mapped yet, keep mapped_tool_id as None
                        logger.debug(f"Slot {slot} not mapped yet")
                    except Exception as e:
                        logger.debug(f"Failed to resolve slot {slot}: {e}")

        except Exception as e:
            logger.warning(f"Failed to resolve mapped tool IDs: {e}")

        return slot_info_map

    async def _collect_from_capabilities(
        self,
        exclude_slots: Optional[set] = None,
        user_message: Optional[str] = None,
    ) -> tuple:
        """
        Auto-inject capability pack tools using RAG search when possible.

        Strategy:
        - If user_message is provided, try RAG search first (top-15 tools)
        - On RAG hit: return matched tools, skip full list
        - On RAG miss: return empty (no relevant tools)
        - On RAG error or no user_message: fallback to full ToolListService

        Returns:
            Tuple of (slot_info_map, rag_status)
            rag_status: "hit" | "miss" | "error"
        """
        slot_info_map: Dict[str, ToolSlotInfo] = {}
        exclude_slots = exclude_slots or set()

        # Try RAG search when user_message is available
        if user_message:
            try:
                from backend.app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                    RAG_HIT,
                    RAG_MISS,
                )

                svc = ToolEmbeddingService()
                matches, rag_status = await svc.search(user_message, top_k=15)

                if rag_status == RAG_HIT:
                    for match in matches:
                        if match.tool_id in exclude_slots:
                            continue
                        slot_info_map[match.tool_id] = ToolSlotInfo(
                            slot=match.tool_id,
                            description=match.description,
                            source="capability",
                            priority=30,
                        )
                    logger.info(
                        f"RAG hit: injected {len(slot_info_map)} tools "
                        f"(top: {matches[0].tool_id} @ {matches[0].similarity:.3f})"
                    )
                    return slot_info_map, "hit"

                if rag_status == RAG_MISS:
                    logger.info("RAG miss: no relevant tools found")
                    return {}, "miss"

            except Exception as e:
                logger.warning(f"Tool RAG failed, falling back to full list: {e}")

        # Fallback: get ALL tools from ToolListService
        try:
            from backend.app.services.tool_list_service import ToolListService

            tool_svc = ToolListService()
            all_tools = tool_svc.get_all_tools()

            for tool in all_tools:
                if tool.tool_id in exclude_slots:
                    continue
                if not tool.description:
                    continue
                slot_info_map[tool.tool_id] = ToolSlotInfo(
                    slot=tool.tool_id,
                    description=tool.description,
                    source="capability",
                    priority=30,
                )

        except Exception as e:
            logger.warning(f"Failed to collect capability tools: {e}")

        return slot_info_map, "error"

    def format_for_prompt(
        self,
        slot_info_map: Dict[str, ToolSlotInfo],
        include_policy: bool = True,
        include_mapped_tool: bool = True,
        include_relevance_score: bool = False,
    ) -> str:
        """
        Format slot information for LLM prompt injection

        Args:
            slot_info_map: Slot info map
            include_policy: Whether to include policy information
            include_mapped_tool: Whether to include mapped tool_id

        Returns:
            Formatted string for prompt injection
        """
        if not slot_info_map:
            return ""

        lines = ["[AVAILABLE_TOOL_SLOTS]"]
        lines.append(
            "The following tool slots are available for this Playbook. Use slot names instead of concrete tool_id."
        )
        lines.append("")

        # Group by source
        playbook_slots = {
            s: i for s, i in slot_info_map.items() if i.source == "playbook"
        }
        workspace_slots = {
            s: i for s, i in slot_info_map.items() if i.source == "workspace"
        }
        project_slots = {
            s: i for s, i in slot_info_map.items() if i.source == "project"
        }
        capability_slots = {
            s: i for s, i in slot_info_map.items() if i.source == "capability"
        }

        # Sort by priority first, then relevance score (design requirement: priority > relevance)
        def sort_key(item):
            slot, info = item
            # Primary sort: priority (descending, higher priority first)
            priority_score = info.priority
            # Secondary sort: relevance_score (descending, higher relevance first)
            relevance_score = (
                info.relevance_score
                if (include_relevance_score and info.relevance_score is not None)
                else 0.0
            )
            # Return tuple for multi-level sort: (priority, relevance_score) both descending
            return (-priority_score, -relevance_score)

        # Playbook-defined slots (priority)
        if playbook_slots:
            lines.append("## Priority Use (From Playbook Definition):")
            sorted_playbook = sorted(playbook_slots.items(), key=sort_key)
            for slot, info in sorted_playbook:
                lines.extend(
                    self._format_slot_info(
                        slot,
                        info,
                        include_policy,
                        include_mapped_tool,
                        include_relevance_score,
                    )
                )
            lines.append("")

        # Project-level slots
        if project_slots:
            lines.append("## Project Level Mapping:")
            sorted_project = sorted(project_slots.items(), key=sort_key)
            for slot, info in sorted_project:
                lines.extend(
                    self._format_slot_info(
                        slot,
                        info,
                        include_policy,
                        include_mapped_tool,
                        include_relevance_score,
                    )
                )
            lines.append("")

        # Workspace-level slots
        if workspace_slots:
            lines.append("## Workspace Level Mapping:")
            sorted_workspace = sorted(workspace_slots.items(), key=sort_key)
            for slot, info in sorted_workspace:
                lines.extend(
                    self._format_slot_info(
                        slot,
                        info,
                        include_policy,
                        include_mapped_tool,
                        include_relevance_score,
                    )
                )
            lines.append("")

        # Capability-injected slots (lowest priority, auto-discovered)
        if capability_slots:
            lines.append("## Installed Capabilities:")
            sorted_cap = sorted(capability_slots.items(), key=sort_key)
            for slot, info in sorted_cap:
                lines.extend(
                    self._format_slot_info(
                        slot,
                        info,
                        include_policy,
                        include_mapped_tool,
                        include_relevance_score,
                    )
                )
            lines.append("")

        lines.append("[/AVAILABLE_TOOL_SLOTS]")
        return "\n".join(lines)

    def _format_slot_info(
        self,
        slot: str,
        info: ToolSlotInfo,
        include_policy: bool,
        include_mapped_tool: bool,
        include_relevance_score: bool = False,
    ) -> List[str]:
        """Format a single slot info for prompt"""
        lines = []
        lines.append(f"- **{slot}**")

        # Show relevance score if available
        if include_relevance_score and info.relevance_score is not None:
            score_str = f"{info.relevance_score:.2f}"
            lines.append(f"  - Relevance: {score_str}")

        if info.description:
            lines.append(f"  - Description: {info.description}")

        if include_policy and info.policy:
            policy_parts = []
            policy_parts.append(f"risk={info.policy.risk_level}")
            policy_parts.append(f"env={info.policy.env}")
            if info.policy.requires_preview:
                policy_parts.append("requires_preview=true")
            lines.append(f"  - Policy: {', '.join(policy_parts)}")

        if include_mapped_tool and info.mapped_tool_id:
            lines.append(f"  - Mapped to: {info.mapped_tool_id}")

        return lines


# Global instance
_collector_instance: Optional[ToolSlotInfoCollector] = None


def get_tool_slot_info_collector(store=None) -> ToolSlotInfoCollector:
    """
    Get global ToolSlotInfoCollector instance

    Args:
        store: Optional MindscapeStore instance

    Returns:
        ToolSlotInfoCollector instance
    """
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = ToolSlotInfoCollector(store=store)
    return _collector_instance
