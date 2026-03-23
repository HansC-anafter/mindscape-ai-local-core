"""
Execution Plan Builder

Generates execution plans based on user messages and determines side_effect levels.
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from ...models.workspace import SideEffectLevel, ExecutionPlan, TaskPlan
from ...services.conversation.plan_builder_core.pack_policy import (
    check_pack_tools_configured as check_pack_tools_configured_helper,
    determine_side_effect_level as determine_side_effect_level_helper,
    get_pack_id_from_playbook_code as get_pack_id_from_playbook_code_helper,
    is_pack_available as is_pack_available_helper,
)
from ...services.conversation.plan_builder_core.rule_based import (
    build_rule_based_task_plans,
    collect_effective_playbook_codes,
    resolve_available_packs,
)
from ...services.conversation.plan_builder_core.runtime import (
    ensure_external_backend_loaded as ensure_external_backend_loaded_helper,
    finalize_execution_plan,
    select_model_for_plan as select_model_for_plan_helper,
)
from ...services.capability_registry import get_registry
from backend.app.services.pack_info_collector import PackInfoCollector
from backend.app.services.external_backend import (
    validate_mindscape_boundary,
    filter_mindscape_results,
)
from ...shared.llm_provider_helper import get_llm_provider_from_settings
from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


class PlanBuilder:
    """Build execution plans and determine pack side-effect policy."""

    def __init__(
        self,
        store,
        default_locale: str = "en",
        capability_profile: Optional[str] = None,
        stage_router: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize PlanBuilder."""
        self.store = store
        self.default_locale = default_locale
        self.capability_profile = capability_profile
        self.stage_router = stage_router
        self.model_name = model_name  # Direct model name (highest priority)
        from ...services.config_store import ConfigStore

        self.config_store = ConfigStore()
        self.external_backend = None
        self._external_backend_loaded = False
        # Cache LLMProviderManager to avoid recreating it on every call
        self._llm_manager_cache: Dict[str, Any] = {}  # profile_id -> LLMProviderManager

    def _select_model_for_plan(
        self, risk_level: str = "read", profile_id: Optional[str] = None
    ) -> str:
        """Delegate model selection to the extracted runtime helper."""
        return select_model_for_plan_helper(
            self,
            risk_level=risk_level,
            profile_id=profile_id,
        )

    async def _ensure_external_backend_loaded(self, profile_id: Optional[str] = None):
        """Delegate external backend loading to the extracted runtime helper."""
        await ensure_external_backend_loaded_helper(self, profile_id=profile_id)

    async def _create_or_link_phase(
        self,
        execution_plan: "ExecutionPlan",
        project_id: str,
        message_id: str,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Retained facade for compatibility with callers/tests."""
        from ...services.conversation.plan_builder_core.runtime import (
            create_or_link_phase as create_or_link_phase_helper,
        )

        await create_or_link_phase_helper(
            self,
            execution_plan=execution_plan,
            project_id=project_id,
            message_id=message_id,
            project_assignment_decision=project_assignment_decision,
        )

    def is_pack_available(self, pack_id: str) -> bool:
        """Delegate pack availability checks to the extracted helper."""
        return is_pack_available_helper(pack_id)

    def check_pack_tools_configured(self, pack_id: str) -> bool:
        """Delegate tool-configuration checks to the extracted helper."""
        return check_pack_tools_configured_helper(pack_id)

    def determine_side_effect_level(self, pack_id: str) -> SideEffectLevel:
        """Delegate side-effect policy lookup to the extracted helper."""
        return determine_side_effect_level_helper(pack_id)

    async def _generate_llm_plan(
        self,
        message: str,
        files: List[str],
        workspace_id: str,
        profile_id: str,
        available_packs: List[str],
        project_id: Optional[str] = None,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> List[TaskPlan]:
        """
        Generate execution plan using LLM

        Args:
            message: User message
            files: List of file IDs
            workspace_id: Workspace ID
            profile_id: User profile ID
            available_packs: List of available pack IDs
            thread_id: Optional thread ID for thread-scoped context

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
                from backend.app.shared.llm_provider_helper import (
                    create_llm_provider_manager,
                )

                self._llm_manager_cache[cache_key] = create_llm_provider_manager(
                    openai_key=config.agent_backend.openai_api_key,
                    anthropic_key=config.agent_backend.anthropic_api_key,
                    vertex_api_key=config.agent_backend.vertex_api_key,
                    vertex_project_id=config.agent_backend.vertex_project_id,
                    vertex_location=config.agent_backend.vertex_location,
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
                logger.warning(
                    f"LLM provider not available: {e}, falling back to rule-based planning"
                )
                return []

            from backend.app.services.conversation.context_builder import ContextBuilder
            from backend.app.services.stores.postgres.timeline_items_store import (
                PostgresTimelineItemsStore,
            )

            timeline_items_store = PostgresTimelineItemsStore()

            # Use _select_model_for_plan to select model (with fallback to chat_model)
            # Determine risk_level from project_assignment_decision or default to "read"
            risk_level = "read"
            if project_assignment_decision:
                # Try to infer risk_level from project_assignment_decision
                # This is a simplified version - full implementation would check actual tool policies
                pass

            model_name = self._select_model_for_plan(
                risk_level=risk_level, profile_id=profile_id
            )
            if not model_name or model_name.strip() == "":
                raise ValueError(
                    "LLM model is empty. Please select a valid model in the system settings panel."
                )

            context_builder = ContextBuilder(
                store=self.store,
                timeline_items_store=timeline_items_store,
                model_name=model_name,
            )

            workspace = None
            try:
                workspace = await self.store.get_workspace(workspace_id)
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
                mode="planning",
                thread_id=thread_id,
                side_chain_mode="auto",
            )

            project_context_str = ""
            if project_id and project_assignment_decision:
                try:
                    from backend.app.services.project.project_manager import (
                        ProjectManager,
                    )

                    project_manager = ProjectManager(self.store)
                    project = await project_manager.get_project(
                        project_id, workspace_id=workspace_id
                    )

                    if project:
                        recent_phases_str = ""
                        try:
                            from backend.app.services.project.project_phase_manager import (
                                ProjectPhaseManager,
                            )

                            phase_manager = ProjectPhaseManager(store=self.store)
                            recent_phases = await phase_manager.get_recent_phases(
                                project_id=project_id, limit=3
                            )
                            if recent_phases:
                                phase_lines = [
                                    f"  {i+1}. Phase {p.kind}: {p.summary[:80]}"
                                    for i, p in enumerate(recent_phases)
                                ]
                                recent_phases_str = (
                                    "\n- Related previous phases:\n"
                                    + "\n".join(phase_lines)
                                )
                        except Exception as e:
                            logger.debug(
                                f"Failed to load recent phases for project {project_id}: {e}"
                            )

                        assignment_relation = project_assignment_decision.get(
                            "relation", "unknown"
                        )
                        confidence = project_assignment_decision.get("confidence", 0.0)
                        reasoning = project_assignment_decision.get("reasoning", "N/A")

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
                        "workspace_description": (
                            workspace.description if workspace else None
                        ),
                        "workspace_mode": workspace.mode if workspace else None,
                        "conversation_history": [],
                        "user_language": self.default_locale,
                    }

                    cloud_result = await asyncio.wait_for(
                        self.external_backend.retrieve_context(
                            workspace_id=workspace_id,
                            message=message,
                            workspace_context=workspace_context_dict,
                            profile_id=profile_id,
                            session_id=f"{workspace_id}_{profile_id}",
                        ),
                        timeout=1.5,
                    )

                    client_kind = "mindscape_edge"
                    is_valid, violations = validate_mindscape_boundary(
                        client_kind=client_kind,
                        memory_policy={"allow_chat_history_write": False},
                        request_metadata={},
                    )

                    if violations:
                        logger.warning(
                            f"Boundary rule violations detected: {violations}"
                        )

                    if cloud_result.get("success") and cloud_result.get(
                        "retrieved_snippets"
                    ):
                        filtered_snippets = filter_mindscape_results(
                            cloud_result.get("retrieved_snippets", []), client_kind
                        )

                        if filtered_snippets:
                            cloud_rag_context = f"""

---

## Cloud Retrieved Knowledge (for reference only):
{chr(10).join([f"- {s.get('content', '')[:cloud_rag_char_limit]}..." for s in filtered_snippets[:cloud_rag_snippet_limit]])}"""

                            logger.info(
                                f"Cloud RAG retrieval completed: {len(filtered_snippets)} snippets, confidence={cloud_result.get('retrieval_metadata', {}).get('confidence_score', 0):.2f}"
                            )

                except asyncio.TimeoutError:
                    logger.warning(
                        "Cloud RAG retrieval timeout (1.5s), using local context only"
                    )
                except Exception as e:
                    logger.warning(
                        f"Cloud RAG retrieval failed, using local context only: {e}"
                    )

            pack_collector = PackInfoCollector(self.store.db_path)
            installed_packs = pack_collector.get_all_installed_packs(workspace_id)
            installed_pack_ids = {p["pack_id"] for p in installed_packs}

            registry = get_registry()
            for pack_id in available_packs:
                if pack_id not in installed_pack_ids:
                    capability_info = registry.capabilities.get(pack_id)
                    if capability_info:
                        manifest = capability_info.get("manifest", {})
                        installed_packs.append(
                            {
                                "pack_id": pack_id,
                                "display_name": manifest.get("display_name", pack_id),
                                "description": manifest.get("description", ""),
                                "side_effect_level": manifest.get(
                                    "side_effect_level", "readonly"
                                ),
                                "manifest": manifest,
                                "metadata": {},
                            }
                        )

            filtered_packs = [
                p for p in installed_packs if p.get("pack_id") in available_packs
            ]

            from backend.app.services.pack_suggester import PackSuggester

            pack_suggester = PackSuggester()
            detected_packs = pack_suggester.suggest_packs(message, available_packs)
            detected_pack_ids = (
                {s["pack_id"] for s in detected_packs} if detected_packs else set()
            )

            pack_descriptions = pack_collector.build_pack_description_list(
                filtered_packs
            )

            if not pack_descriptions or pack_descriptions == "No packs available":
                pack_descriptions = "\n".join(
                    [
                        f"- {pack_id}: Available pack (check registry for details)"
                        for pack_id in available_packs
                    ]
                )

            logger.info(
                f"Built pack_descriptions for {len(filtered_packs)} packs, available_packs={len(available_packs)}, pack_descriptions length={len(pack_descriptions)} chars"
            )

            intent_hint = ""
            if detected_pack_ids:
                detected_pack_list = list(detected_pack_ids)
                intent_hint = f"\n\nKeyword-based suggestions: {', '.join(detected_pack_list)} (for reference only, analyze full message content)"

            message_length = len(message)
            has_numbered_list = any(
                char.isdigit() and char in message for char in "123456789"
            )
            has_team_mentions = any(
                term in message for term in ["團隊", "团队", "team", "能力", "能力包"]
            )

            context_notes = []
            if message_length > 500:
                context_notes.append(
                    "Long message, may contain multiple capability or requirement descriptions"
                )
            if has_numbered_list:
                context_notes.append(
                    "Message contains numbered list, may describe multiple different capabilities/teams"
                )
            if has_team_mentions:
                context_notes.append(
                    "Message explicitly mentions 'team' or 'capability', need to identify all mentioned capabilities"
                )

            context_note_str = (
                "\n".join([f"- {note}" for note in context_notes])
                if context_notes
                else ""
            )

            schema_description = f"""Analyze the user message AND the conversation history to generate an execution plan by matching them with the available capability packs.

**Guidelines:**

1. **Scenario A: Capability Discovery**
   - If the user asks what you can do or what tools are available, return tasks for packs that specialize in listing or describing capabilities.
   - Do not execute action-oriented tasks, just inform the user.

2. **Scenario B: Action Execution**
   - Identify ALL relevant packs that can fulfill the request based on their descriptions.
   - If multiple packs are relevant to a single request, return tasks for ALL of them.
   - Match capabilities based on what the pack DOES (its purpose and impact), not just keyword matching.

3. **Orchestration & Workflow Selection:**
   - Prefer playbooks that represent a complete, high-level workflow (e.g., "complete_workflow", "page_assembly") over individual, granular playbooks when the user request is broad.
   - Use specialized, focused playbooks only when the user explicitly requests a single, specific operation or is working on a specific part of an existing item.

4. **Task Structure:**
   - Every task MUST include a valid `pack_id` from the available packs list below.
   - Return a JSON object with a "tasks" key containing an ARRAY of task objects.
   - NEVER return a null or empty `pack_id`.

Available packs:
{pack_descriptions}

Execution plan structure:
{{
  "tasks": [
    {{
      "pack_id": "Valid pack identifier from the list below (REQUIRED)",
      "task_type": "Specific action type (e.g., 'generate_content', 'analyze_data', 'extract_intents')",
      "params": {{
        "source": "message/file",
        "description": "Short summary of the specific task"
      }},
      "reason": "Clear justification based on the user's intent and the pack's purpose",
      "confidence": 0.0-1.0
    }}
  ]
}}

**Important Principles:**
- Semantic Matching: Deeply understand the user's intended GOAL.
- Completeness: Ensure every mentioned requirement is addressed by a corresponding pack.
- Diversity: If a request can be fulfilled in multiple ways (e.g., exporting to different formats), offer all relevant options.
- Context Awareness: Leverage recent Assistant suggestions and conversation history to refine pack selection."""

            context_with_history = f"""{workspace_context}{cloud_rag_context}

---

User message: {message}
Files provided: {len(files)} file(s)
Available packs: {', '.join(available_packs)}{intent_hint}

Message analysis hints:
{context_note_str if context_note_str else "- Standard user request"}"""

            estimated_context_tokens = context_builder.estimate_token_count(
                context_with_history, model_name=None
            )
            estimated_schema_tokens = context_builder.estimate_token_count(
                schema_description, model_name=None
            )
            estimated_pack_tokens = context_builder.estimate_token_count(
                pack_descriptions, model_name=None
            )
            estimated_cloud_tokens = (
                context_builder.estimate_token_count(cloud_rag_context, model_name=None)
                if cloud_rag_context
                else 0
            )
            total_estimated_tokens = (
                estimated_context_tokens
                + estimated_schema_tokens
                + estimated_pack_tokens
                + estimated_cloud_tokens
            )

            max_tokens_for_planning = 10000

            if total_estimated_tokens > max_tokens_for_planning:
                logger.warning(
                    f"Total context too long ({total_estimated_tokens} tokens > {max_tokens_for_planning}), applying v2 multi-stage progressive degradation"
                )

                if (
                    detected_pack_ids
                    and len(detected_pack_ids) < len(available_packs)
                    and len(detected_pack_ids) > 0
                ):
                    logger.info(
                        f"Stage 2: Reducing pack descriptions (keeping {len(detected_pack_ids)} keyword-suggested packs with full descriptions)"
                    )
                    suggested_packs = [
                        p
                        for p in filtered_packs
                        if p.get("pack_id") in detected_pack_ids
                    ]
                    other_packs = [
                        p
                        for p in filtered_packs
                        if p.get("pack_id") not in detected_pack_ids
                    ]

                    suggested_descriptions = pack_collector.build_pack_description_list(
                        suggested_packs
                    )
                    other_pack_ids = "\n".join(
                        [
                            f"- {p.get('pack_id')}: (omitted description)"
                            for p in other_packs
                        ]
                    )

                    pack_descriptions = f"""{suggested_descriptions}

Other available packs (omitted for brevity):
{other_pack_ids}"""

                    estimated_pack_tokens = context_builder.estimate_token_count(
                        pack_descriptions, model_name=None
                    )
                    total_estimated_tokens = (
                        estimated_context_tokens
                        + estimated_schema_tokens
                        + estimated_pack_tokens
                        + estimated_cloud_tokens
                    )
                    logger.info(
                        f"After Stage 2: pack={estimated_pack_tokens} tokens, total={total_estimated_tokens} tokens"
                    )
                else:
                    logger.info(
                        f"Stage 2: No keyword-suggested packs or all packs suggested, keeping all pack descriptions (detected_pack_ids={len(detected_pack_ids) if detected_pack_ids else 0}, available_packs={len(available_packs)})"
                    )

                if (
                    total_estimated_tokens > max_tokens_for_planning
                    and cloud_rag_context
                ):
                    if cloud_rag_snippet_limit > 3:
                        logger.info(
                            "Stage 3: Reducing cloud RAG context (5 to 3 snippets, 200 to 100 chars)"
                        )
                        cloud_rag_snippet_limit = 3
                        cloud_rag_char_limit = 100
                        cloud_rag_context = (
                            cloud_rag_context[: len(cloud_rag_context) // 2]
                            + "\n(Cloud context truncated for token budget)"
                        )
                        estimated_cloud_tokens = context_builder.estimate_token_count(
                            cloud_rag_context, model_name=None
                        )
                        total_estimated_tokens = (
                            estimated_context_tokens
                            + estimated_schema_tokens
                            + estimated_pack_tokens
                            + estimated_cloud_tokens
                        )
                        logger.info(
                            f"After Stage 3: cloud={estimated_cloud_tokens} tokens, total={total_estimated_tokens} tokens"
                        )

                context_with_history = f"""{project_context_str}{workspace_context}{cloud_rag_context}

---

User message: {message}
Files provided: {len(files)} file(s)
Available packs: {', '.join(available_packs)}{intent_hint}

Message analysis hints:
{context_note_str if context_note_str else "- Standard user request"}"""

                estimated_context_tokens = context_builder.estimate_token_count(
                    context_with_history, model_name=None
                )
                total_estimated_tokens = (
                    estimated_context_tokens + estimated_schema_tokens
                )

                if total_estimated_tokens > max_tokens_for_planning:
                    logger.warning(
                        f"Context still exceeds limit after v2 progressive degradation ({total_estimated_tokens} tokens > {max_tokens_for_planning}). "
                        f"Proceeding - extract function or LLM provider should handle gracefully. "
                        f"Components: workspace={estimated_context_tokens}, schema={estimated_schema_tokens}, pack={estimated_pack_tokens}, cloud={estimated_cloud_tokens}"
                    )
                else:
                    logger.info(
                        f"Context fits after v2 progressive degradation: total={total_estimated_tokens} tokens"
                    )

            example_output = {
                "tasks": [
                    {
                        "pack_id": "content_drafting",
                        "task_type": "generate_draft",
                        "params": {"source": "message"},
                        "reason": "Message describes 'course design team' that helps design complete course flow with opening, theory, practice, Q&A - matches content_drafting pack's purpose",
                        "confidence": 0.9,
                    },
                    {
                        "pack_id": "storyboard",
                        "task_type": "generate_storyboard",
                        "params": {"source": "message"},
                        "reason": "Message describes 'teaching script & Storyboard team' for creating teaching scripts, shot lists, and video content - directly matches storyboard pack",
                        "confidence": 0.85,
                    },
                    {
                        "pack_id": "daily_planning",
                        "task_type": "generate_tasks",
                        "params": {"source": "message"},
                        "reason": "Message describes 'course project management / event PM team' for breaking down projects into tasks, timelines, and checklists - matches daily_planning pack",
                        "confidence": 0.8,
                    },
                    {
                        "pack_id": "habit_learning",
                        "task_type": "generate_plan",
                        "params": {"source": "message"},
                        "reason": "Message describes 'habit and execution coaching team' for long-term habit building and continuous execution coaching - matches habit_learning pack",
                        "confidence": 0.75,
                    },
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
                    execution_id=f"plan_{profile_id}_{int(_utc_now().timestamp())}",
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
                logger.warning(
                    f"Failed to start trace node for LLM plan generation: {e}"
                )

            llm_start_time = _utc_now()
            try:
                result = await extract(
                    text=context_with_history,
                    schema_description=schema_description,
                    example_output=example_output,
                    llm_provider=llm_provider,
                )
                llm_end_time = _utc_now()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)

                # End trace node for successful LLM call
                if trace_node_id and trace_id:
                    try:
                        trace_recorder = get_trace_recorder()
                        # Estimate token count (simplified)
                        input_tokens = (
                            len(context_with_history.split()) * 1.3
                        )  # Rough estimate
                        output_tokens = len(str(result).split()) * 1.3
                        total_tokens = int(input_tokens + output_tokens)

                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.SUCCESS,
                            output_data={
                                "tasks_count": len(
                                    result.get("extracted_data", {}).get("tasks", [])
                                ),
                            },
                            cost_tokens=total_tokens,
                            latency_ms=latency_ms,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to end trace node for LLM plan generation: {e}"
                        )
            except Exception as e:
                llm_end_time = _utc_now()
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
                        logger.warning(
                            f"Failed to end trace node for failed LLM plan generation: {e2}"
                        )
                raise

            extracted_data = result.get("extracted_data", {})
            logger.info(f"Full extracted_data: {extracted_data}")

            tasks_data = extracted_data.get("tasks", [])
            if not tasks_data and isinstance(extracted_data, dict):
                if "pack_id" in extracted_data:
                    logger.warning(
                        f"LLM returned single task object instead of tasks array, wrapping it. This should not happen - LLM should return {{'tasks': [...]}} format"
                    )
                    tasks_data = [extracted_data]
                else:
                    logger.warning(
                        f"tasks key not found in extracted_data, keys: {list(extracted_data.keys())}"
                    )

            if tasks_data and len(tasks_data) == 1:
                logger.warning(
                    f"LLM returned only 1 task. For requests like 'export file', multiple tasks (content_drafting, storyboard, core_export) should be returned. Current task: {tasks_data[0].get('pack_id')}"
                )

            logger.info(
                f"Extracted {len(tasks_data)} tasks from LLM response: {tasks_data}"
            )
            logger.info(f"Available packs: {available_packs}")

            task_plans = []
            for task_data in tasks_data:
                pack_id = task_data.get("pack_id")
                if not pack_id or pack_id not in available_packs:
                    logger.warning(
                        f"LLM suggested unavailable pack {pack_id}, skipping"
                    )
                    continue

                if not self.is_pack_available(pack_id):
                    logger.warning(f"Pack {pack_id} is not available, skipping")
                    continue
                if not self.check_pack_tools_configured(pack_id):
                    logger.warning(f"Pack {pack_id} tools are not configured, skipping")
                    continue

                level = self.determine_side_effect_level(pack_id)

                confidence = task_data.get("confidence", 0.8)
                if (
                    not isinstance(confidence, (int, float))
                    or confidence < 0
                    or confidence > 1
                ):
                    logger.warning(
                        f"Invalid confidence value {confidence} for pack {pack_id}, using default 0.8"
                    )
                    confidence = 0.8

                llm_analysis = {
                    "confidence": float(confidence),
                    "reason": task_data.get("reason", ""),
                    "content_tags": [],
                    "analysis_summary": task_data.get("reason", "")[:200],
                }

                logger.info(
                    f"Task {pack_id}: confidence={confidence:.2f}, reason={task_data.get('reason', '')[:50]}"
                )

                params = task_data.get("params", {})
                params["llm_analysis"] = llm_analysis

                task_plan = TaskPlan(
                    pack_id=pack_id,
                    task_type=task_data.get("task_type", "execute"),
                    params=params,
                    side_effect_level=level.value,
                    auto_execute=(level == SideEffectLevel.READONLY),
                    requires_cta=(level != SideEffectLevel.READONLY),
                )
                task_plans.append(task_plan)

            logger.info(f"LLM generated {len(task_plans)} task plans")
            return task_plans

        except Exception as e:
            logger.warning(
                f"Failed to generate LLM plan: {e}, falling back to rule-based planning"
            )
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
        available_playbooks: Optional[
            List[Dict[str, Any]]
        ] = None,  # Keep for backward compatibility
        routing_decision: Optional[Any] = None,  # IntentRoutingDecision
        thread_id: Optional[str] = None,
    ) -> ExecutionPlan:
        """Generate an execution plan using LLM-first, rule-based fallback."""
        import uuid

        playbooks_to_use = (
            effective_playbooks
            if effective_playbooks is not None
            else available_playbooks
        )

        if effective_playbooks is None and available_playbooks is not None:
            logger.warning(
                f"PlanBuilder.generate_execution_plan: effective_playbooks not provided, "
                f"using deprecated available_playbooks. This will be deprecated in future versions."
            )

        task_plans = []

        available_packs = resolve_available_packs(self.is_pack_available)

        if playbooks_to_use:
            effective_playbook_codes = collect_effective_playbook_codes(
                playbooks_to_use
            )
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
                    project_assignment_decision=project_assignment_decision,
                    thread_id=thread_id,
                )
                if llm_plans:
                    task_plans.extend(llm_plans)
                    logger.info(
                        f"PlanBuilder: LLM generated {len(llm_plans)} task plans"
                    )
                    if task_plans:
                        execution_plan = ExecutionPlan(
                            message_id=message_id or str(uuid.uuid4()),
                            workspace_id=workspace_id,
                            tasks=task_plans,
                            created_at=_utc_now(),
                            project_id=project_id,
                            project_assignment_decision=project_assignment_decision,
                        )
                        return await finalize_execution_plan(
                            self,
                            execution_plan=execution_plan,
                            project_id=project_id,
                            message_id=message_id or execution_plan.message_id,
                            project_assignment_decision=project_assignment_decision,
                            playbooks_to_use=playbooks_to_use,
                        )
                else:
                    logger.info(
                        "PlanBuilder: LLM planning returned no plans, falling back to rule-based"
                    )
            except Exception as e:
                logger.warning(
                    f"PlanBuilder: LLM planning failed: {e}, falling back to rule-based"
                )

        task_plans.extend(
            build_rule_based_task_plans(
                builder=self,
                message=message,
                files=files,
            )
        )

        execution_plan = ExecutionPlan(
            message_id=message_id or str(uuid.uuid4()),
            workspace_id=workspace_id,
            tasks=task_plans,
            created_at=_utc_now(),
            project_id=project_id,
            project_assignment_decision=project_assignment_decision,
        )

        return await finalize_execution_plan(
            self,
            execution_plan=execution_plan,
            project_id=project_id,
            message_id=message_id or execution_plan.message_id,
            project_assignment_decision=project_assignment_decision,
            playbooks_to_use=playbooks_to_use,
        )

    def _get_pack_id_from_playbook_code(self, playbook_code: str) -> Optional[str]:
        """Delegate playbook-to-pack resolution to the extracted helper."""
        return get_pack_id_from_playbook_code_helper(playbook_code)
