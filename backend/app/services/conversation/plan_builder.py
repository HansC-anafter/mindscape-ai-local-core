"""
Execution Plan Builder

Generates execution plans based on user messages and determines side_effect levels.
"""

import logging
import os
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from ...models.workspace import SideEffectLevel, ExecutionPlan, TaskPlan
from ...capabilities.registry import get_registry
from backend.app.services.pack_info_collector import PackInfoCollector
from backend.app.services.external_backend import load_external_backend, validate_mindscape_boundary, filter_mindscape_results
from ...shared.llm_provider_helper import get_llm_provider_from_settings
from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


class PlanBuilder:
    """
    Builds execution plans based on user messages and file inputs

    Determines side_effect_level for packs and generates TaskPlan objects.
    """

    def __init__(
        self,
        store,
        default_locale: str = "en",
        capability_profile: Optional[str] = None,
        stage_router: Optional[Any] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize PlanBuilder

        Args:
            store: MindscapeStore instance (for db_path access)
            default_locale: Default locale for i18n
            capability_profile: Capability profile override (optional)
            stage_router: Stage router instance (optional)
            model_name: Direct model name override (highest priority, optional)
        """
        self.store = store
        self.default_locale = default_locale
        self.capability_profile = capability_profile
        self.stage_router = stage_router
        self.model_name = model_name  # Direct model name (highest priority)
        from ...services.config_store import ConfigStore
        self.config_store = ConfigStore(db_path=store.db_path)
        self.external_backend = None
        self._external_backend_loaded = False
        # Cache LLMProviderManager to avoid recreating it on every call
        self._llm_manager_cache: Dict[str, Any] = {}  # profile_id -> LLMProviderManager

    def _select_model_for_plan(self, risk_level: str = "read", profile_id: Optional[str] = None) -> str:
        """
        Select model for plan generation stage

        Priority:
        1. Direct model_name (highest priority)
        2. stage_router selection
        3. capability_profile selection
        4. SystemSettings selection
        5. chat_model fallback (final fallback)

        Args:
            risk_level: Risk level ("read", "write", "publish")
            profile_id: Profile ID for LLM provider

        Returns:
            Model name
        """
        # 1. Direct model_name (highest priority)
        if self.model_name:
            return self.model_name

        # 2. stage_router selection
        if self.stage_router:
            try:
                from backend.app.services.conversation.capability_profile import CapabilityProfileRegistry
                profile = self.stage_router.get_profile_for_stage("plan_generation", risk_level=risk_level)
                registry = CapabilityProfileRegistry()
                # Get or reuse cached LLMProviderManager
                cache_key = profile_id or "default-user"
                if cache_key not in self._llm_manager_cache:
                    from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                    config = self.config_store.get_or_create_config(cache_key)
                    self._llm_manager_cache[cache_key] = create_llm_provider_manager(
                        openai_key=config.agent_backend.openai_api_key,
                        anthropic_key=config.agent_backend.anthropic_api_key,
                        vertex_api_key=config.agent_backend.vertex_api_key,
                        vertex_project_id=config.agent_backend.vertex_project_id,
                        vertex_location=config.agent_backend.vertex_location
                    )
                llm_manager = self._llm_manager_cache[cache_key]
                model_name = registry.select_model(profile, llm_manager, profile_id=profile_id)
                if model_name:
                    return model_name
            except Exception as e:
                logger.debug(f"Failed to use stage_router: {e}, trying next option")

        # 3. capability_profile selection
        if self.capability_profile:
            try:
                from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
                profile = CapabilityProfile(self.capability_profile)
                registry = CapabilityProfileRegistry()
                # Reuse cached LLMProviderManager
                cache_key = profile_id or "default-user"
                if cache_key not in self._llm_manager_cache:
                    from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                    config = self.config_store.get_or_create_config(cache_key)
                    self._llm_manager_cache[cache_key] = create_llm_provider_manager(
                        openai_key=config.agent_backend.openai_api_key,
                        anthropic_key=config.agent_backend.anthropic_api_key,
                        vertex_api_key=config.agent_backend.vertex_api_key,
                        vertex_project_id=config.agent_backend.vertex_project_id,
                        vertex_location=config.agent_backend.vertex_location
                    )
                llm_manager = self._llm_manager_cache[cache_key]
                model_name = registry.select_model(profile, llm_manager, profile_id=profile_id)
                if model_name:
                    return model_name
            except Exception as e:
                logger.debug(f"Failed to use capability_profile: {e}, trying next option")

        # 4. SystemSettings selection
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore
            from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
            settings_store = SystemSettingsStore()
            mapping = settings_store.get_capability_profile_mapping()
            profile_name = mapping.get("plan_generation", "precise")
            profile = CapabilityProfile(profile_name)
            registry = CapabilityProfileRegistry()
            # Reuse cached LLMProviderManager
            cache_key = profile_id or "default-user"
            if cache_key not in self._llm_manager_cache:
                from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                config = self.config_store.get_or_create_config(cache_key)
                self._llm_manager_cache[cache_key] = create_llm_provider_manager(
                    openai_key=config.agent_backend.openai_api_key,
                    anthropic_key=config.agent_backend.anthropic_api_key,
                    vertex_api_key=config.agent_backend.vertex_api_key,
                    vertex_project_id=config.agent_backend.vertex_project_id,
                    vertex_location=config.agent_backend.vertex_location
                )
            llm_manager = self._llm_manager_cache[cache_key]
            model_name = registry.select_model(profile, llm_manager, profile_id=profile_id)
            if model_name:
                return model_name
        except Exception as e:
            logger.debug(f"Failed to use SystemSettings: {e}, trying next option")

        # 5. chat_model fallback (final fallback)
        from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
        model_name = get_model_name_from_chat_model()
        if model_name:
            logger.debug(f"Using chat_model fallback: {model_name}")
            return model_name

        # Ultimate fallback
        logger.warning("PlanBuilder: All model selection methods failed, using default gpt-4")
        return "gpt-4"

    async def _ensure_external_backend_loaded(self, profile_id: Optional[str] = None):
        """
        Load ExternalBackend if configured (lazy loading)

        Args:
            profile_id: Optional profile ID for loading from user config
        """
        if self._external_backend_loaded:
            return

        self._external_backend_loaded = True

        try:
            # Try to load from user config first
            if profile_id:
                config = self.config_store.get_or_create_config(profile_id)
                external_config = getattr(config, 'external_backend', None)

                if external_config and isinstance(external_config, dict):
                    self.external_backend = await load_external_backend(external_config)
                    if self.external_backend:
                        logger.info(f"Loaded external backend from user config for profile {profile_id}")
                        return

            driver = os.getenv("EXTERNAL_BACKEND_DRIVER")
            if driver:
                options = {
                    "base_url": os.getenv("EXTERNAL_BACKEND_URL"),
                    "api_key": os.getenv("EXTERNAL_BACKEND_API_KEY"),
                    "timeout": float(os.getenv("EXTERNAL_BACKEND_TIMEOUT", "1.5"))
                }
                self.external_backend = await load_external_backend({
                    "driver": driver,
                    "options": options
                })
                if self.external_backend:
                    logger.info("Loaded external backend from environment variables")
                    return

            logger.debug("No external backend configured, will skip cloud-enhanced retrieval")

        except Exception as e:
            logger.warning(f"Failed to load external backend: {e}, will skip cloud-enhanced retrieval")
            self.external_backend = None

    async def _create_or_link_phase(
        self,
        execution_plan: "ExecutionPlan",
        project_id: str,
        message_id: str,
        project_assignment_decision: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Create or link phase for execution plan

        Args:
            execution_plan: ExecutionPlan object
            project_id: Project ID
            message_id: Message ID
            project_assignment_decision: Project assignment decision metadata
        """
        try:
            from backend.app.services.project.project_phase_manager import ProjectPhaseManager
            phase_manager = ProjectPhaseManager(store=self.store)

            assignment_relation = project_assignment_decision.get("relation") if project_assignment_decision else None
            phase_kind = "revision" if assignment_relation == "same_project" else "initial_brief"

            phase = await phase_manager.create_phase(
                project_id=project_id,
                message_id=message_id,
                summary=execution_plan.plan_summary or execution_plan.user_request_summary or "",
                kind=phase_kind,
                workspace_id=execution_plan.workspace_id,
                execution_plan_id=execution_plan.id
            )

            execution_plan.phase_id = phase.id
            execution_plan.project_id = project_id

            logger.info(
                f"Created phase {phase.id} for project {project_id}, "
                f"kind={phase_kind}, message_id={message_id}"
            )

        except Exception as e:
            logger.warning(f"Failed to create phase for execution plan: {e}", exc_info=True)
            # Don't fail execution plan creation if phase creation fails
            pass

    def is_pack_available(self, pack_id: str) -> bool:
        """
        Check if a pack is installed and available

        Args:
            pack_id: Pack identifier (capability code)

        Returns:
            True if pack is installed and available, False otherwise
        """
        try:
            import sqlite3
            import json

            db_path = self.store.db_path

            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.cursor()
                    cursor.execute('SELECT pack_id FROM installed_packs WHERE pack_id = ?', (pack_id,))
                    row = cursor.fetchone()
                    if row:
                        # Pack is installed
                        return True
                finally:
                    conn.close()

            registry = get_registry()
            capability_info = registry.capabilities.get(pack_id)
            if capability_info:
                # Pack exists in registry, consider it available
                # (installation check is optional for built-in packs)
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check pack availability for {pack_id}: {e}")
            return False

    def check_pack_tools_configured(self, pack_id: str) -> bool:
        """
        Check if required tools for a pack are configured

        Args:
            pack_id: Pack identifier (capability code)

        Returns:
            True if all required tools are configured, False otherwise
        """
        try:
            registry = get_registry()
            capability_info = registry.capabilities.get(pack_id)
            if not capability_info:
                return False

            manifest = capability_info.get('manifest', {})
            tools = manifest.get('tools', [])

            # For now, assume tools are available if pack is in registry
            # In the future, we can check specific tool configurations
            # (e.g., WordPress API keys, Notion tokens, etc.)
            if tools:
                # Basic check: if pack has tools defined, assume they're available
                # More sophisticated checks can be added later
                return True

            return True  # Pack has no tools, so it's available

        except Exception as e:
            logger.warning(f"Failed to check pack tools for {pack_id}: {e}")
            return False

    def determine_side_effect_level(self, pack_id: str) -> SideEffectLevel:
        """
        Determine side effect level for a pack

        Conservative default: if not specified, treat as readonly

        Priority:
        1. Load from installed_packs table metadata (if installed)
        2. Load from capability registry manifest.yaml
        3. Default to READONLY (conservative)

        Args:
            pack_id: Pack identifier (capability code)

        Returns:
            SideEffectLevel enum value
        """
        try:
            # Try to load from installed_packs table first
            import sqlite3
            import json

            db_path = self.store.db_path

            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.cursor()
                    cursor.execute('SELECT metadata FROM installed_packs WHERE pack_id = ?', (pack_id,))
                    row = cursor.fetchone()
                    if row:
                        metadata_str = row['metadata']
                        if metadata_str:
                            metadata = json.loads(metadata_str)
                            if isinstance(metadata, dict) and 'side_effect_level' in metadata:
                                level_str = metadata['side_effect_level']
                                try:
                                    return SideEffectLevel(level_str)
                                except ValueError:
                                    logger.warning(f"Invalid side_effect_level '{level_str}' for pack {pack_id}, using default")
                finally:
                    conn.close()

            # Try to load from capability registry manifest
            registry = get_registry()
            capability_info = registry.capabilities.get(pack_id)
            if capability_info:
                manifest = capability_info.get('manifest', {})
                if 'side_effect_level' in manifest:
                    level_str = manifest['side_effect_level']
                    try:
                        return SideEffectLevel(level_str)
                    except ValueError:
                        logger.warning(f"Invalid side_effect_level '{level_str}' for pack {pack_id}, using default")

            # Conservative default: readonly
            logger.debug(f"No side_effect_level found for pack {pack_id}, defaulting to readonly")
            return SideEffectLevel.READONLY

        except Exception as e:
            logger.warning(f"Failed to determine side_effect_level for pack {pack_id}: {e}, using default")
            return SideEffectLevel.READONLY

    async def _generate_llm_plan(
        self,
        message: str,
        files: List[str],
        workspace_id: str,
        profile_id: str,
        available_packs: List[str],
        project_id: Optional[str] = None,
        project_assignment_decision: Optional[Dict[str, Any]] = None
    ) -> List[TaskPlan]:
        """
        Generate execution plan using LLM

        Args:
            message: User message
            files: List of file IDs
            workspace_id: Workspace ID
            profile_id: User profile ID
            available_packs: List of available pack IDs

        Returns:
            List of TaskPlan objects
        """
        try:
            from ...capabilities.core_llm.services.structured import extract
            from ...services.agent_runner import LLMProviderManager
            import os
            import json

            config = self.config_store.get_or_create_config(profile_id)
            # Reuse cached LLMProviderManager
            cache_key = profile_id or "default-user"
            if cache_key not in self._llm_manager_cache:
                from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                self._llm_manager_cache[cache_key] = create_llm_provider_manager(
                    openai_key=config.agent_backend.openai_api_key,
                    anthropic_key=config.agent_backend.anthropic_api_key,
                    vertex_api_key=config.agent_backend.vertex_api_key,
                    vertex_project_id=config.agent_backend.vertex_project_id,
                    vertex_location=config.agent_backend.vertex_location
                )
            llm_manager = self._llm_manager_cache[cache_key]

            # Get user's selected chat model to determine provider
            from backend.app.services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            provider_name = None

            if chat_setting:
                provider_name = chat_setting.metadata.get("provider")
                if not provider_name:
                    model_name = str(chat_setting.value)
                    if "gemini" in model_name.lower():
                        provider_name = "vertex-ai"
                    elif "gpt" in model_name.lower() or "text-" in model_name.lower():
                        provider_name = "openai"
                    elif "claude" in model_name.lower():
                        provider_name = "anthropic"

            try:
                llm_provider = get_llm_provider_from_settings(llm_manager)
            except ValueError as e:
                logger.warning(f"LLM provider not available: {e}, falling back to rule-based planning")
                return []

            from backend.app.services.conversation.context_builder import ContextBuilder
            from ...services.stores.timeline_items_store import TimelineItemsStore

            timeline_items_store = TimelineItemsStore(self.store.db_path)

            # Use _select_model_for_plan to select model (with fallback to chat_model)
            # Determine risk_level from project_assignment_decision or default to "read"
            risk_level = "read"
            if project_assignment_decision:
                # Try to infer risk_level from project_assignment_decision
                # This is a simplified version - full implementation would check actual tool policies
                pass

            model_name = self._select_model_for_plan(risk_level=risk_level, profile_id=profile_id)
            if not model_name or model_name.strip() == "":
                raise ValueError(
                    "LLM model is empty. Please select a valid model in the system settings panel."
                )

            context_builder = ContextBuilder(
                store=self.store,
                timeline_items_store=timeline_items_store,
                model_name=model_name
            )

            workspace = None
            try:
                workspace = self.store.get_workspace(workspace_id)
            except Exception as e:
                logger.debug(f"Could not get workspace object: {e}")

            max_tokens_for_planning = 10000
            workspace_context_budget = int(max_tokens_for_planning * 0.6)

            workspace_context = await context_builder.build_planning_context(
                workspace_id=workspace_id,
                message=message,
                profile_id=profile_id,
                workspace=workspace,
                target_tokens=workspace_context_budget,
                mode="planning"
            )

            project_context_str = ""
            if project_id and project_assignment_decision:
                try:
                    from backend.app.services.project.project_manager import ProjectManager
                    project_manager = ProjectManager(self.store)
                    project = await project_manager.get_project(project_id, workspace_id=workspace_id)

                    if project:
                        recent_phases_str = ""
                        try:
                            from backend.app.services.project.project_phase_manager import ProjectPhaseManager
                            phase_manager = ProjectPhaseManager(store=self.store)
                            recent_phases = await phase_manager.get_recent_phases(project_id=project_id, limit=3)
                            if recent_phases:
                                phase_lines = [f"  {i+1}. Phase {p.kind}: {p.summary[:80]}" for i, p in enumerate(recent_phases)]
                                recent_phases_str = "\n- Related previous phases:\n" + "\n".join(phase_lines)
                        except Exception as e:
                            logger.debug(f"Failed to load recent phases for project {project_id}: {e}")

                        assignment_relation = project_assignment_decision.get('relation', 'unknown')
                        confidence = project_assignment_decision.get('confidence', 0.0)
                        reasoning = project_assignment_decision.get('reasoning', 'N/A')

                        project_context_str = f"""

[PROJECT CONTEXT]

- Active project_id: {project_id}
- Project title: 「{project.title}」
- Project type: {project.type}
- Project summary: {project.metadata.get('summary', 'N/A') if project.metadata else 'N/A'}
- This message is classified as: 「{assignment_relation}」, confidence = {confidence:.2f}
- Reasoning: {reasoning}
{recent_phases_str}

IMPORTANT: When interpreting the user's request, treat it as a continuation of the above Project, unless the user explicitly states they want to start a completely different work item.
"""
                except Exception as e:
                    logger.warning(f"Failed to build project context: {e}")

            cloud_rag_context = ""
            cloud_rag_snippet_limit = 5
            cloud_rag_char_limit = 200

            await self._ensure_external_backend_loaded(profile_id)
            if self.external_backend:
                try:
                    workspace_context_dict = {
                        "workspace_title": workspace.title if workspace else None,
                        "workspace_description": workspace.description if workspace else None,
                        "workspace_mode": workspace.mode if workspace else None,
                        "conversation_history": [],
                        "user_language": self.default_locale
                    }

                    cloud_result = await asyncio.wait_for(
                        self.external_backend.retrieve_context(
                            workspace_id=workspace_id,
                            message=message,
                            workspace_context=workspace_context_dict,
                            profile_id=profile_id,
                            session_id=f"{workspace_id}_{profile_id}"
                        ),
                        timeout=1.5
                    )

                    client_kind = "mindscape_edge"
                    is_valid, violations = validate_mindscape_boundary(
                        client_kind=client_kind,
                        memory_policy={"allow_chat_history_write": False},
                        request_metadata={}
                    )

                    if violations:
                        logger.warning(f"Boundary rule violations detected: {violations}")

                    if cloud_result.get("success") and cloud_result.get("retrieved_snippets"):
                        filtered_snippets = filter_mindscape_results(
                            cloud_result.get("retrieved_snippets", []),
                            client_kind
                        )

                        if filtered_snippets:
                            cloud_rag_context = f"""

---

## Cloud Retrieved Knowledge (for reference only):
{chr(10).join([f"- {s.get('content', '')[:cloud_rag_char_limit]}..." for s in filtered_snippets[:cloud_rag_snippet_limit]])}"""

                            logger.info(f"Cloud RAG retrieval completed: {len(filtered_snippets)} snippets, confidence={cloud_result.get('retrieval_metadata', {}).get('confidence_score', 0):.2f}")

                except asyncio.TimeoutError:
                    logger.warning("Cloud RAG retrieval timeout (1.5s), using local context only")
                except Exception as e:
                    logger.warning(f"Cloud RAG retrieval failed, using local context only: {e}")

            pack_collector = PackInfoCollector(self.store.db_path)
            installed_packs = pack_collector.get_all_installed_packs(workspace_id)
            installed_pack_ids = {p['pack_id'] for p in installed_packs}

            registry = get_registry()
            for pack_id in available_packs:
                if pack_id not in installed_pack_ids:
                    capability_info = registry.capabilities.get(pack_id)
                    if capability_info:
                        manifest = capability_info.get('manifest', {})
                        installed_packs.append({
                            'pack_id': pack_id,
                            'display_name': manifest.get('display_name', pack_id),
                            'description': manifest.get('description', ''),
                            'side_effect_level': manifest.get('side_effect_level', 'readonly'),
                            'manifest': manifest,
                            'metadata': {}
                        })

            filtered_packs = [
                p for p in installed_packs
                if p.get('pack_id') in available_packs
            ]

            from backend.app.services.pack_suggester import PackSuggester
            pack_suggester = PackSuggester()
            detected_packs = pack_suggester.suggest_packs(message, available_packs)
            detected_pack_ids = {s['pack_id'] for s in detected_packs} if detected_packs else set()

            pack_descriptions = pack_collector.build_pack_description_list(filtered_packs)

            if not pack_descriptions or pack_descriptions == "No packs available":
                pack_descriptions = "\n".join([
                    f"- {pack_id}: Available pack (check registry for details)"
                    for pack_id in available_packs
                ])

            logger.info(f"Built pack_descriptions for {len(filtered_packs)} packs, available_packs={len(available_packs)}, pack_descriptions length={len(pack_descriptions)} chars")

            intent_hint = ""
            if detected_pack_ids:
                detected_pack_list = list(detected_pack_ids)
                intent_hint = f"\n\nKeyword-based suggestions: {', '.join(detected_pack_list)} (for reference only, analyze full message content)"

            message_length = len(message)
            has_numbered_list = any(char.isdigit() and char in message for char in "123456789")
            has_team_mentions = any(term in message for term in ["團隊", "团队", "team", "能力", "能力包"])

            context_notes = []
            if message_length > 500:
                context_notes.append("Long message, may contain multiple capability or requirement descriptions")
            if has_numbered_list:
                context_notes.append("Message contains numbered list, may describe multiple different capabilities/teams")
            if has_team_mentions:
                context_notes.append("Message explicitly mentions 'team' or 'capability', need to identify all mentioned capabilities")

            context_note_str = "\n".join([f"- {note}" for note in context_notes]) if context_notes else ""

            schema_description = f"""Analyze the user message AND the conversation history (especially recent Assistant replies) to generate an execution plan.

**Two distinct scenarios:**

**Scenario A: User asks for a LIST of available tools/capabilities**
- Examples: "What tools can you use to generate files?" / "What capabilities do you have?"
- Your response: Return tasks for packs that can LIST or DESCRIBE capabilities (e.g., research, tooling)
- Do NOT execute file generation tasks, just inform about available options

**Scenario B: User wants ACTION - actually generate/create something**
- Examples: "Generate a file for me!" / "Output a file" / "Create a report" / "Export file for me"
- Your response:
  1. Identify ALL relevant packs that can fulfill the request
  2. For file generation requests (e.g., "export file"), consider ALL file-export capable packs:
     - content_drafting (for .docx/.pdf documents)
     - storyboard (for .pptx presentations)
     - core_export (for general file exports)
     - daily_planning (for .xlsx/.csv spreadsheets)
  3. Return MULTIPLE tasks (one for each relevant pack), not just one
  4. DO NOT return a single task when multiple packs are relevant

**CRITICAL: For orchestration workflows, prefer complete workflow playbooks:**

**For IG post creation requests:**
- If user says "create IG post" / "創建 IG 貼文" / "幫我創建一個 IG 貼文" / "generate IG post" / "new IG post"
- **RECOMMENDED**: Use 'ig' capability (cloud) with playbook 'ig_complete_workflow' (action='create_post_workflow')
- This executes the complete workflow: validation → content check → hashtag → asset validation → export pack generation
- **DO NOT** use individual playbooks like 'ig_template_engine' or 'ig_hashtag_manager' for complete post creation requests

**For specific, focused IG post tasks (on existing posts):**
- If user says "just generate hashtags" / "只生成 hashtag" / "幫我加 hashtag" / "generate hashtags for this post"
  → Use 'ig' capability (cloud) with playbook 'ig_hashtag_manager'
- If user says "validate content" / "驗證內容" / "檢查內容" / "check content"
  → Use 'ig' capability (cloud) with playbook 'ig_content_checker'
- If user says "generate template" / "生成模板" / "create template"
  → Use 'ig' capability (cloud) with playbook 'ig_template_engine'
- If user says "validate assets" / "驗證素材" / "check assets"
  → Use 'ig' capability (cloud) with playbook 'ig_asset_manager'
- If user says "generate export pack" / "生成發文包" / "create export pack"
  → Use 'ig' capability (cloud) with playbook 'ig_export_pack_generator'
- **Key indicators for individual playbook usage**:
  - User uses words like "just", "only", "只", "僅", "幫我加", "幫我檢查"
  - User specifies a single, specific task
  - User is working on an existing post (mentions "this post", "這篇貼文", or provides post_path)
  - User explicitly requests only one operation

**For web page generation requests:**
- If user says "create web page" / "生成網頁" / "幫我創建一個網頁" / "generate web page" / "new web page"
- **RECOMMENDED**: Use 'web_generation' pack with playbook 'multi_page_assembly' or 'page_assembly' (for complete workflow)
- This executes the complete workflow: page_outline → page_sections → page_assembly
- **DO NOT** use individual playbooks like 'page_outline' alone for complete web page creation requests

**For specific, focused web page tasks:**
- If user says "just create page outline" / "只生成頁面結構" / "generate outline only"
  → Use 'web_generation' pack with playbook 'page_outline'
- If user says "generate page sections" / "生成頁面區塊" / "create sections only"
  → Use 'web_generation' pack with playbook 'page_sections'
- **Key indicators for individual playbook usage**:
  - User uses words like "just", "only", "只", "僅"
  - User specifies a single, specific task
  - User is working on an existing project/page

The user message might be:
1. A direct action request (e.g., "Help me design a course", "Export file for me")
2. A description of multiple AI teams/capabilities (e.g., "I have 4 teams: course design, storyboard, project management...")
3. A combination of both

**CRITICAL: Also analyze Assistant replies in the conversation history:**
- If the Assistant mentioned specific playbooks, tools, or capabilities in recent replies, extract those suggestions
- If the Assistant recommended specific actions (e.g., "I can use content_drafting to generate a file"), use those recommendations
- The Assistant's suggestions in conversation history are often more accurate than just analyzing the user message alone

Your task:
- Understand the SEMANTIC meaning of BOTH the user message AND recent Assistant replies
- Determine if this is Scenario A (list request) or Scenario B (action request)
- Extract playbook suggestions from Assistant replies if they exist
- If the message describes multiple capabilities/teams, identify ALL of them
- Map each capability to the appropriate pack from the available packs below
- **CRITICAL for Scenario B (action requests)**: Return MULTIPLE tasks when the request can be fulfilled by multiple packs
  - Example: "export file" → return tasks for: content_drafting, storyboard, core_export (if all are relevant)
  - Example: "help me export file" → return tasks for ALL file-export capable packs that match the context
- Generate one task for each relevant pack
- **CRITICAL**: pack_id MUST be a valid pack identifier from the available packs list below, NEVER null or empty
- **IMPORTANT**: The "tasks" array should contain MULTIPLE tasks when the request involves multiple capabilities or when multiple packs can fulfill a single action request. Do NOT return a single task object - always return an array of tasks.

Available packs:
{pack_descriptions}

Execution plan structure (pack_id is REQUIRED and must be valid):
{{
  "tasks": [
    {{
      "pack_id": "MUST be a pack identifier from available packs above (REQUIRED, cannot be null)",
      "task_type": "task type (e.g., 'extract_intents', 'generate_tasks', 'generate_storyboard', 'generate_draft')",
      "params": {{
        "source": "message or file",
        "files": ["file_id1", "file_id2"]  // if applicable
      }},
      "reason": "why this pack should be executed based on message content",
      "confidence": 0.0-1.0  // confidence score for this task (0.0 = low, 1.0 = high)
    }},
    {{
      "pack_id": "another_pack_id",
      "task_type": "another_task_type",
      "params": {{"source": "message"}},
      "reason": "another reason"
    }}
    // ... more tasks if multiple packs are relevant
  ]
}}

**CRITICAL FORMAT REQUIREMENT**:
- The response MUST be a JSON object with a "tasks" key containing an ARRAY
- The "tasks" array can contain 1 or more task objects
- NEVER return a single task object directly - it must always be wrapped in {{"tasks": [...]}}
- If multiple packs are relevant (e.g., "export file" can use content_drafting, storyboard, core_export), return ALL of them in the tasks array

Important principles:
1. **pack_id is REQUIRED**: Every task MUST have a valid pack_id from the available packs list. If you cannot find a matching pack, do NOT create a task with null pack_id.
2. **Semantic understanding**: Understand what the user wants to DO, not just what words they used
3. **Multiple capabilities**: If the message describes multiple teams/capabilities, create multiple tasks (one for each)
4. **Completeness for action requests**: Don't miss any capability mentioned in the message. For action requests like "export file" or "help me export file" (Scenario B), you MUST consider ALL relevant file-export capable packs:
   - content_drafting (for .docx/.pdf documents)
   - storyboard (for .pptx presentations)
   - core_export (for general file exports)
   - daily_planning (for .xlsx/.csv spreadsheets)
   Return tasks for ALL of them if they are relevant to the request, not just one.
5. **Pack matching**: Match capabilities to packs based on what the pack DOES, not just keywords. Read each pack's description carefully.
6. **Reason clarity**: Each task's reason should explain how the message content relates to the pack's purpose
7. **ALWAYS return tasks array**: The response MUST be in the format {{"tasks": [...]}}, never return a single task object. The tasks array can contain 1 or more tasks, but must always be an array.
8. **Orchestration preference**: For complete creation requests (IG post, web page), prefer complete workflow playbooks over individual playbooks. Only use individual playbooks for specific, focused tasks."""

            context_with_history = f"""{workspace_context}{cloud_rag_context}

---

User message: {message}
Files provided: {len(files)} file(s)
Available packs: {', '.join(available_packs)}{intent_hint}

Message analysis hints:
{context_note_str if context_note_str else "- Standard user request"}"""

            estimated_context_tokens = context_builder.estimate_token_count(context_with_history, model_name=None)
            estimated_schema_tokens = context_builder.estimate_token_count(schema_description, model_name=None)
            estimated_pack_tokens = context_builder.estimate_token_count(pack_descriptions, model_name=None)
            estimated_cloud_tokens = context_builder.estimate_token_count(cloud_rag_context, model_name=None) if cloud_rag_context else 0
            total_estimated_tokens = estimated_context_tokens + estimated_schema_tokens + estimated_pack_tokens + estimated_cloud_tokens

            max_tokens_for_planning = 10000

            if total_estimated_tokens > max_tokens_for_planning:
                logger.warning(f"Total context too long ({total_estimated_tokens} tokens > {max_tokens_for_planning}), applying v2 multi-stage progressive degradation")

                if detected_pack_ids and len(detected_pack_ids) < len(available_packs) and len(detected_pack_ids) > 0:
                    logger.info(f"Stage 2: Reducing pack descriptions (keeping {len(detected_pack_ids)} keyword-suggested packs with full descriptions)")
                    suggested_packs = [p for p in filtered_packs if p.get('pack_id') in detected_pack_ids]
                    other_packs = [p for p in filtered_packs if p.get('pack_id') not in detected_pack_ids]

                    suggested_descriptions = pack_collector.build_pack_description_list(suggested_packs)
                    other_pack_ids = "\n".join([f"- {p.get('pack_id')}: (omitted description)" for p in other_packs])

                    pack_descriptions = f"""{suggested_descriptions}

Other available packs (omitted for brevity):
{other_pack_ids}"""

                    estimated_pack_tokens = context_builder.estimate_token_count(pack_descriptions, model_name=None)
                    total_estimated_tokens = estimated_context_tokens + estimated_schema_tokens + estimated_pack_tokens + estimated_cloud_tokens
                    logger.info(f"After Stage 2: pack={estimated_pack_tokens} tokens, total={total_estimated_tokens} tokens")
                else:
                    logger.info(f"Stage 2: No keyword-suggested packs or all packs suggested, keeping all pack descriptions (detected_pack_ids={len(detected_pack_ids) if detected_pack_ids else 0}, available_packs={len(available_packs)})")

                if total_estimated_tokens > max_tokens_for_planning and cloud_rag_context:
                    if cloud_rag_snippet_limit > 3:
                        logger.info("Stage 3: Reducing cloud RAG context (5 to 3 snippets, 200 to 100 chars)")
                        cloud_rag_snippet_limit = 3
                        cloud_rag_char_limit = 100
                        cloud_rag_context = cloud_rag_context[:len(cloud_rag_context) // 2] + "\n(Cloud context truncated for token budget)"
                        estimated_cloud_tokens = context_builder.estimate_token_count(cloud_rag_context, model_name=None)
                        total_estimated_tokens = estimated_context_tokens + estimated_schema_tokens + estimated_pack_tokens + estimated_cloud_tokens
                        logger.info(f"After Stage 3: cloud={estimated_cloud_tokens} tokens, total={total_estimated_tokens} tokens")

                context_with_history = f"""{project_context_str}{workspace_context}{cloud_rag_context}

---

User message: {message}
Files provided: {len(files)} file(s)
Available packs: {', '.join(available_packs)}{intent_hint}

Message analysis hints:
{context_note_str if context_note_str else "- Standard user request"}"""

                estimated_context_tokens = context_builder.estimate_token_count(context_with_history, model_name=None)
                total_estimated_tokens = estimated_context_tokens + estimated_schema_tokens

                if total_estimated_tokens > max_tokens_for_planning:
                    logger.warning(
                        f"Context still exceeds limit after v2 progressive degradation ({total_estimated_tokens} tokens > {max_tokens_for_planning}). "
                        f"Proceeding - extract function or LLM provider should handle gracefully. "
                        f"Components: workspace={estimated_context_tokens}, schema={estimated_schema_tokens}, pack={estimated_pack_tokens}, cloud={estimated_cloud_tokens}"
                    )
                else:
                    logger.info(f"Context fits after v2 progressive degradation: total={total_estimated_tokens} tokens")

            example_output = {
                "tasks": [
                    {
                        "pack_id": "content_drafting",
                        "task_type": "generate_draft",
                        "params": {"source": "message"},
                        "reason": "Message describes 'course design team' that helps design complete course flow with opening, theory, practice, Q&A - matches content_drafting pack's purpose",
                        "confidence": 0.9
                    },
                    {
                        "pack_id": "storyboard",
                        "task_type": "generate_storyboard",
                        "params": {"source": "message"},
                        "reason": "Message describes 'teaching script & Storyboard team' for creating teaching scripts, shot lists, and video content - directly matches storyboard pack",
                        "confidence": 0.85
                    },
                    {
                        "pack_id": "daily_planning",
                        "task_type": "generate_tasks",
                        "params": {"source": "message"},
                        "reason": "Message describes 'course project management / event PM team' for breaking down projects into tasks, timelines, and checklists - matches daily_planning pack",
                        "confidence": 0.8
                    },
                    {
                        "pack_id": "habit_learning",
                        "task_type": "generate_plan",
                        "params": {"source": "message"},
                        "reason": "Message describes 'habit and execution coaching team' for long-term habit building and continuous execution coaching - matches habit_learning pack",
                        "confidence": 0.75
                    }
                ]
            }

            # Start trace node for LLM call
            trace_node_id = None
            trace_id = None
            try:
                trace_recorder = get_trace_recorder()
                # Try to get trace_id from execution context if available
                # For now, we'll create a new trace if needed
                # In the future, this should be passed from ConversationOrchestrator
                trace_id = trace_recorder.create_trace(
                    workspace_id=workspace_id,
                    execution_id=f"plan_{profile_id}_{int(datetime.utcnow().timestamp())}",
                    user_id=profile_id,
                )
                trace_node_id = trace_recorder.start_node(
                    trace_id=trace_id,
                    node_type=TraceNodeType.LLM,
                    name=f"llm:plan_generation",
                    input_data={
                        "message": message[:200],
                        "model_name": model_name,
                        "available_packs_count": len(available_packs),
                    },
                    metadata={
                        "model_name": model_name,
                        "capability_profile": self.capability_profile,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to start trace node for LLM plan generation: {e}")

            llm_start_time = datetime.utcnow()
            try:
                result = await extract(
                    text=context_with_history,
                    schema_description=schema_description,
                    example_output=example_output,
                    llm_provider=llm_provider
                )
                llm_end_time = datetime.utcnow()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)

                # End trace node for successful LLM call
                if trace_node_id and trace_id:
                    try:
                        trace_recorder = get_trace_recorder()
                        # Estimate token count (simplified)
                        input_tokens = len(context_with_history.split()) * 1.3  # Rough estimate
                        output_tokens = len(str(result).split()) * 1.3
                        total_tokens = int(input_tokens + output_tokens)

                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.SUCCESS,
                            output_data={
                                "tasks_count": len(result.get("extracted_data", {}).get("tasks", [])),
                            },
                            cost_tokens=total_tokens,
                            latency_ms=latency_ms,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to end trace node for LLM plan generation: {e}")
            except Exception as e:
                llm_end_time = datetime.utcnow()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)

                # End trace node for failed LLM call
                if trace_node_id and trace_id:
                    try:
                        trace_recorder = get_trace_recorder()
                        import traceback
                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.FAILED,
                            error_message=str(e)[:500],
                            error_stack=traceback.format_exc(),
                            latency_ms=latency_ms,
                        )
                    except Exception as e2:
                        logger.warning(f"Failed to end trace node for failed LLM plan generation: {e2}")
                raise

            extracted_data = result.get("extracted_data", {})
            logger.info(f"Full extracted_data: {extracted_data}")

            tasks_data = extracted_data.get("tasks", [])
            if not tasks_data and isinstance(extracted_data, dict):
                if "pack_id" in extracted_data:
                    logger.warning(f"LLM returned single task object instead of tasks array, wrapping it. This should not happen - LLM should return {{'tasks': [...]}} format")
                    tasks_data = [extracted_data]
                else:
                    logger.warning(f"tasks key not found in extracted_data, keys: {list(extracted_data.keys())}")

            if tasks_data and len(tasks_data) == 1:
                logger.warning(f"LLM returned only 1 task. For requests like 'export file', multiple tasks (content_drafting, storyboard, core_export) should be returned. Current task: {tasks_data[0].get('pack_id')}")

            logger.info(f"Extracted {len(tasks_data)} tasks from LLM response: {tasks_data}")
            logger.info(f"Available packs: {available_packs}")

            task_plans = []
            for task_data in tasks_data:
                pack_id = task_data.get("pack_id")
                if not pack_id or pack_id not in available_packs:
                    logger.warning(f"LLM suggested unavailable pack {pack_id}, skipping")
                    continue

                if not self.is_pack_available(pack_id):
                    logger.warning(f"Pack {pack_id} is not available, skipping")
                    continue
                if not self.check_pack_tools_configured(pack_id):
                    logger.warning(f"Pack {pack_id} tools are not configured, skipping")
                    continue

                level = self.determine_side_effect_level(pack_id)

                confidence = task_data.get("confidence", 0.8)
                if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                    logger.warning(f"Invalid confidence value {confidence} for pack {pack_id}, using default 0.8")
                    confidence = 0.8

                llm_analysis = {
                    "confidence": float(confidence),
                    "reason": task_data.get("reason", ""),
                    "content_tags": [],
                    "analysis_summary": task_data.get("reason", "")[:200]
                }

                logger.info(f"Task {pack_id}: confidence={confidence:.2f}, reason={task_data.get('reason', '')[:50]}")

                params = task_data.get("params", {})
                params["llm_analysis"] = llm_analysis

                task_plan = TaskPlan(
                    pack_id=pack_id,
                    task_type=task_data.get("task_type", "execute"),
                    params=params,
                    side_effect_level=level.value,
                    auto_execute=(level == SideEffectLevel.READONLY),
                    requires_cta=(level != SideEffectLevel.READONLY)
                )
                task_plans.append(task_plan)

            logger.info(f"LLM generated {len(task_plans)} task plans")
            return task_plans

        except Exception as e:
            logger.warning(f"Failed to generate LLM plan: {e}, falling back to rule-based planning")
            return []

    async def generate_execution_plan(
        self,
        message: str,
        files: List[str],
        workspace_id: str,
        profile_id: str,
        message_id: Optional[str] = None,
        use_llm: bool = True,
        project_id: Optional[str] = None,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
        effective_playbooks: Optional[List[Dict[str, Any]]] = None,
        available_playbooks: Optional[List[Dict[str, Any]]] = None,  # Keep for backward compatibility
        routing_decision: Optional[Any] = None  # IntentRoutingDecision
    ) -> ExecutionPlan:
        """
        Generate execution plan for message

        Priority: LLM-based planning (if use_llm=True), falls back to rule-based planning if LLM fails.
        Checks side_effect_level and pack availability for each pack.

        Args:
            message: User message
            files: List of file IDs
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID (optional)
            use_llm: Whether to use LLM-based planning as primary (default: True, falls back to rule-based if LLM fails)
            effective_playbooks: Pre-resolved effective playbooks (from PlaybookScopeResolver)
            available_playbooks: Available playbooks (deprecated, kept for backward compatibility)

        Returns:
            ExecutionPlan object with planned tasks
        """
        from datetime import datetime
        import uuid

        playbooks_to_use = effective_playbooks if effective_playbooks is not None else available_playbooks

        if effective_playbooks is None and available_playbooks is not None:
            logger.warning(
                f"PlanBuilder.generate_execution_plan: effective_playbooks not provided, "
                f"using deprecated available_playbooks. This will be deprecated in future versions."
            )

        task_plans = []

        registry = get_registry()
        available_packs = list(registry.capabilities.keys())
        available_packs = [pack_id for pack_id in available_packs if self.is_pack_available(pack_id)]

        if playbooks_to_use:
            effective_playbook_codes = {pb.get("playbook_code") for pb in playbooks_to_use if pb.get("playbook_code")}
            logger.info(
                f"PlanBuilder: Using {len(effective_playbook_codes)} effective playbooks: {list(effective_playbook_codes)[:5]}..."
            )

        if use_llm:
            try:
                llm_plans = await self._generate_llm_plan(
                    message=message,
                    files=files,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    available_packs=available_packs,
                    project_id=project_id,
                    project_assignment_decision=project_assignment_decision
                )
                if llm_plans:
                    task_plans.extend(llm_plans)
                    logger.info(f"PlanBuilder: LLM generated {len(llm_plans)} task plans")
                    if task_plans:
                        execution_plan = ExecutionPlan(
                            message_id=message_id or str(uuid.uuid4()),
                            workspace_id=workspace_id,
                            tasks=task_plans,
                            created_at=datetime.utcnow(),
                            project_id=project_id,
                            project_assignment_decision=project_assignment_decision
                        )

                        if project_id and execution_plan:
                            await self._create_or_link_phase(
                                execution_plan=execution_plan,
                                project_id=project_id,
                                message_id=message_id or execution_plan.message_id,
                                project_assignment_decision=project_assignment_decision
                            )

                        if playbooks_to_use is not None:
                            # Store effective playbooks in a way that to_event_payload can access
                            # ExecutionPlan.to_event_payload() uses getattr(self, "metadata", None)
                            # So we store it as a private attribute that can be accessed via getattr
                            if not hasattr(execution_plan, '_metadata'):
                                execution_plan._metadata = {}
                            execution_plan._metadata["effective_playbooks"] = playbooks_to_use
                            execution_plan._metadata["effective_playbooks_count"] = len(playbooks_to_use)

                        return execution_plan
                else:
                    logger.info("PlanBuilder: LLM planning returned no plans, falling back to rule-based")
            except Exception as e:
                logger.warning(f"PlanBuilder: LLM planning failed: {e}, falling back to rule-based")

        if files:
            pack_id = "semantic_seeds"
            if not self.is_pack_available(pack_id):
                logger.warning(f"Pack {pack_id} is not available, skipping")
            elif not self.check_pack_tools_configured(pack_id):
                logger.warning(f"Pack {pack_id} tools are not configured, skipping")
            else:
                level = self.determine_side_effect_level(pack_id)

                if level == SideEffectLevel.READONLY:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="extract_intents",
                        params={"files": files},
                        side_effect_level=level.value,
                        auto_execute=True,
                        requires_cta=False
                    ))
                elif level == SideEffectLevel.SOFT_WRITE:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="extract_intents",
                        params={"files": files},
                        side_effect_level=level.value,
                        auto_execute=False,
                        requires_cta=True
                    ))
                elif level == SideEffectLevel.EXTERNAL_WRITE:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="extract_intents",
                        params={"files": files},
                        side_effect_level=level.value,
                        auto_execute=False,
                        requires_cta=True
                    ))

        planning_keywords = ["task", "plan", "todo", "planning", "schedule", "待辦", "任務", "計劃"]
        if any(keyword in message.lower() for keyword in planning_keywords):
            pack_id = "daily_planning"
            if not self.is_pack_available(pack_id):
                logger.warning(f"Pack {pack_id} is not available, skipping")
            elif not self.check_pack_tools_configured(pack_id):
                logger.warning(f"Pack {pack_id} tools are not configured, skipping")
            else:
                level = self.determine_side_effect_level(pack_id)

                if level == SideEffectLevel.READONLY:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="generate_tasks",
                        params={"source": "message"},
                        side_effect_level=level.value,
                        auto_execute=True,
                        requires_cta=False
                    ))
                elif level == SideEffectLevel.SOFT_WRITE:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="generate_tasks",
                        params={"source": "message"},
                        side_effect_level=level.value,
                        auto_execute=False,
                        requires_cta=True
                    ))
                elif level == SideEffectLevel.EXTERNAL_WRITE:
                    task_plans.append(TaskPlan(
                        pack_id=pack_id,
                        task_type="generate_tasks",
                        params={"source": "message"},
                        side_effect_level=level.value,
                        auto_execute=False,
                        requires_cta=True
                    ))

        summary_keywords = ["summary", "summarize", "summary of", "摘要", "總結"]
        draft_keywords = ["draft", "草稿", "寫", "generate", "create"]
        if any(keyword in message.lower() for keyword in summary_keywords + draft_keywords):
            pack_id = "content_drafting"
            if not self.is_pack_available(pack_id):
                logger.warning(f"Pack {pack_id} is not available, skipping")
            elif not self.check_pack_tools_configured(pack_id):
                logger.warning(f"Pack {pack_id} tools are not configured, skipping")
            else:
                level = self.determine_side_effect_level(pack_id)
                output_type = "summary" if any(keyword in message.lower() for keyword in summary_keywords) else "draft"

                task_plans.append(TaskPlan(
                    pack_id=pack_id,
                    task_type=f"generate_{output_type}",
                    params={"source": "message", "output_type": output_type},
                    side_effect_level=level.value,
                    auto_execute=False,
                    requires_cta=True
                ))

        execution_plan = ExecutionPlan(
            message_id=message_id or str(uuid.uuid4()),
            workspace_id=workspace_id,
            tasks=task_plans,
            created_at=datetime.utcnow(),
            project_id=project_id,
            project_assignment_decision=project_assignment_decision
        )

        if project_id and execution_plan:
            await self._create_or_link_phase(
                execution_plan=execution_plan,
                project_id=project_id,
                message_id=message_id or execution_plan.message_id,
                project_assignment_decision=project_assignment_decision
            )

        if playbooks_to_use is not None:
            # Store effective playbooks in a way that to_event_payload can access
            # ExecutionPlan.to_event_payload() uses getattr(self, "metadata", None)
            # So we store it as a private attribute that can be accessed via getattr
            if not hasattr(execution_plan, '_metadata'):
                execution_plan._metadata = {}
            execution_plan._metadata["effective_playbooks"] = playbooks_to_use
            execution_plan._metadata["effective_playbooks_count"] = len(playbooks_to_use)

        return execution_plan

    def _get_pack_id_from_playbook_code(self, playbook_code: str) -> Optional[str]:
        """
        Get pack_id from playbook_code

        Strategy:
        1. Check if playbook_code contains pack prefix (e.g., "ig.ig_complete_workflow")
        2. If not, scan all capability packs' manifest.yaml to find which pack contains this playbook
        3. Fallback: check playbook metadata for capability_tags

        Args:
            playbook_code: Playbook code (e.g., "ig_complete_workflow")

        Returns:
            Pack ID (capability_code) if found, None otherwise
        """
        from backend.app.capabilities.registry import get_registry

        registry = get_registry()

        # Strategy 1: If playbook_code contains pack prefix (e.g., "ig.ig_complete_workflow")
        if "." in playbook_code:
            pack_id, _ = playbook_code.split(".", 1)
            if pack_id in registry.list_capabilities():
                return pack_id

        # Strategy 2: Scan all capability packs' manifest.yaml
        for capability_code in registry.list_capabilities():
            capability = registry.get_capability(capability_code)
            if not capability:
                continue

            # Get playbooks list from manifest
            playbooks = registry.get_capability_playbooks(capability_code)

            # Check if playbook_code matches any playbook in this pack
            # Note: get_capability_playbooks returns file names, we need to match against playbook_code
            # Playbook codes are typically the file name without extension
            for playbook_file in playbooks:
                # Remove .json or .yaml extension if present
                playbook_name = playbook_file.replace(".json", "").replace(".yaml", "")
                if playbook_name == playbook_code:
                    return capability_code

        # Strategy 3: Try to find from playbook service (if playbook is loaded)
        try:
            from backend.app.services.playbook_service import PlaybookService
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()
            playbook_service = PlaybookService(store)

            # Try to load playbook and check its metadata
            # Note: This might be slow, so we use it as fallback
            playbook_run = playbook_service.load_playbook_run_sync(playbook_code, workspace_id=None)
            if playbook_run and playbook_run.playbook:
                # Check if playbook metadata has capability_tags or owner_type
                metadata = playbook_run.playbook.metadata
                if hasattr(metadata, 'capability_tags') and metadata.capability_tags:
                    # First capability_tag might indicate the pack
                    for tag in metadata.capability_tags:
                        if tag in registry.list_capabilities():
                            return tag
        except Exception as e:
            logger.debug(f"Failed to get pack_id from playbook service for {playbook_code}: {e}")

        logger.warning(f"Could not find pack_id for playbook_code: {playbook_code}")
        return None
