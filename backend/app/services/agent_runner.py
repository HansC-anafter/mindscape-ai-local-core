"""
Agent Runner Service
Handles AI agent execution with user context and mindscape integration
"""

import os
import asyncio
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, List, Optional, Any
import logging

from backend.app.models.mindscape import (
    MindscapeProfile,
    IntentCard,
    AgentExecution,
    RunAgentRequest,
    AgentResponse,
    MindEvent,
    EventType,
    EventActor,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings

# Import LLM providers from refactored package
from backend.app.services.llm_providers import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    VertexAIProvider,
    OllamaProvider,
    LlamaCppProvider,
    LLMProviderManager,
)

logger = logging.getLogger(__name__)




class AgentPromptBuilder:
    """Builds prompts for different agent types"""

    def __init__(self):
        self.agent_prompts = {
            "planner": {
                "role": "You are an expert project planner and strategist. Help the user break down their goals into actionable steps.",
                "instructions": "Focus on creating clear, prioritized action plans with timelines and dependencies.",
            },
            "writer": {
                "role": "You are a skilled writer and content creator. Help the user craft compelling written content and visual designs.",
                "instructions": "Focus on clarity, engagement, and adapting to the user's communication style. You can also create visual designs using Canva tools when needed for social media posts, marketing materials, or presentations.",
            },
            "visual_design_partner": {
                "role": "You are a visual design partner specializing in creating compelling visual content from text ideas. Help users transform their concepts into professional design assets.",
                "instructions": "Focus on understanding the user's content goals and creating appropriate visual designs. Use Canva tools to generate designs from templates, update text blocks, and export assets in multiple sizes for different platforms (Instagram, Facebook, banners, etc.).",
            },
            "coach": {
                "role": "You are an experienced coach and mentor. Help the user reflect on their progress and overcome challenges.",
                "instructions": "Focus on asking insightful questions, providing encouragement, and helping with personal growth.",
            },
            "coder": {
                "role": "You are an expert software developer. Help the user with programming tasks and technical challenges.",
                "instructions": "Focus on providing clear, well-documented code solutions with explanations.",
            },
        }

    def build_system_prompt(
        self,
        agent_type: str,
        profile: MindscapeProfile,
        active_intents: List[IntentCard],
        workspace: Optional[Any] = None,
    ) -> str:
        """Build system prompt with user context and language policy

        Args:
            agent_type: Type of agent (e.g., "planner", "writer")
            profile: User profile
            active_intents: List of active intent cards
            workspace: Optional workspace object for locale resolution
        """

        agent_config = self.agent_prompts.get(agent_type, self.agent_prompts["planner"])

        prompt_parts = []

        # Agent role
        prompt_parts.append(f"[AGENT_ROLE]\n{agent_config['role']}")
        prompt_parts.append(f"{agent_config['instructions']}\n[/AGENT_ROLE]")

        # Language policy section (using unified template)
        from backend.app.shared.i18n_loader import get_locale_from_context
        from backend.app.shared.prompt_templates import build_language_policy_section

        preferred_language = get_locale_from_context(
            profile=profile, workspace=workspace
        )
        language_policy = build_language_policy_section(preferred_language)
        prompt_parts.append(language_policy)

        # User profile context
        if profile:
            prompt_parts.append("[USER_PROFILE]")
            prompt_parts.append(f"Name: {profile.name}")
            if profile.roles:
                prompt_parts.append(f"Roles: {', '.join(profile.roles)}")
            if profile.domains:
                prompt_parts.append(f"Domains: {', '.join(profile.domains)}")
            if profile.preferences:
                prefs = profile.preferences
                prompt_parts.append(
                    f"Communication Style: {prefs.communication_style.value}"
                )
                prompt_parts.append(f"Response Length: {prefs.response_length.value}")
                # Note: Language preference is now in language policy section above
                # Keep legacy language field for backward compatibility, but it's redundant
                prompt_parts.append(f"Language: {prefs.language}")
            prompt_parts.append("[/USER_PROFILE]")

        # Apply confirmed habits for tools/playbooks (additional context beyond preferences)
        if profile:
            try:
                from backend.app.services.habit_store import HabitStore

                habit_store = HabitStore()
                confirmed_habits = habit_store.get_confirmed_habits(profile.id)

                # Extract tool and playbook preferences from confirmed habits
                tool_preferences = []
                playbook_preferences = []
                agent_type_preferences = []

                for habit in confirmed_habits:
                    if (
                        habit.habit_category.value == "tool_usage"
                        and habit.habit_key == "tool_usage"
                    ):
                        tool_preferences.append(habit.habit_value)
                    elif (
                        habit.habit_category.value == "playbook_usage"
                        and habit.habit_key == "playbook_usage"
                    ):
                        playbook_preferences.append(habit.habit_value)
                    elif (
                        habit.habit_category.value == "tool_usage"
                        and habit.habit_key == "executor_runtime_type"
                    ):
                        agent_type_preferences.append(habit.habit_value)

                # Add to prompt if any preferences found
                if tool_preferences or playbook_preferences or agent_type_preferences:
                    prompt_parts.append("[USER_HABITS]")
                    if agent_type_preferences:
                        # If user has a preferred agent type, suggest it
                        most_common_agent = max(
                            set(agent_type_preferences),
                            key=agent_type_preferences.count,
                        )
                        if most_common_agent == agent_type:
                            prompt_parts.append(
                                f"Note: User frequently uses {agent_type} agent type."
                            )
                    if tool_preferences:
                        common_tools = list(set(tool_preferences))[
                            :5
                        ]  # Top 5 unique tools
                        prompt_parts.append(
                            f"Preferred tools: {', '.join(common_tools)}"
                        )
                    if playbook_preferences:
                        common_playbooks = list(set(playbook_preferences))[
                            :3
                        ]  # Top 3 unique playbooks
                        prompt_parts.append(
                            f"Frequently used playbooks: {', '.join(common_playbooks)}"
                        )
                    prompt_parts.append("[/USER_HABITS]")
            except Exception as e:
                # If habit store is not available, continue without habits
                logger.debug(f"Failed to load confirmed habits for prompt: {e}")

        # Active intents context
        if active_intents:
            prompt_parts.append("[ACTIVE_INTENTS]")
            for intent in active_intents[:5]:
                prompt_parts.append(f"- {intent.title}: {intent.description[:100]}...")
                if intent.priority.value != "medium":
                    prompt_parts.append(f"  Priority: {intent.priority.value}")
                if intent.progress_percentage > 0:
                    prompt_parts.append(f"  Progress: {intent.progress_percentage}%")
            prompt_parts.append("[/ACTIVE_INTENTS]")

        return "\n\n".join(prompt_parts)


class AgentRunner:
    """Main agent execution service"""

    def __init__(self):
        self.store = MindscapeStore()
        self._llm_manager = None
        self.prompt_builder = AgentPromptBuilder()
        # Backend manager will be initialized lazily
        self._backend_manager = None

    @property
    def llm_manager(self):
        """Lazily initialize the provider manager to avoid request-path init spam."""
        if self._llm_manager is None:
            from backend.app.shared.llm_provider_helper import create_llm_provider_manager

            self._llm_manager = create_llm_provider_manager()
        return self._llm_manager

    @property
    def backend_manager(self):
        """Lazy initialization of backend manager"""
        if self._backend_manager is None:
            from backend.app.services.backend_manager import BackendManager

            self._backend_manager = BackendManager(self.store)
        return self._backend_manager

    async def run_agent(
        self, profile_id: str, request: RunAgentRequest
    ) -> AgentResponse:
        """Execute an agent with the given request"""

        execution_id = str(uuid.uuid4())
        start_time = _utc_now()

        execution = AgentExecution(
            id=execution_id,
            profile_id=profile_id,
            agent_type=request.agent_type,
            task=request.task,
            intent_ids=request.intent_ids,
            status="running",
            started_at=start_time,
        )

        try:
            # Get user context
            profile = None
            active_intents = []

            if request.use_mindscape:
                profile = self.store.get_profile(profile_id)
                if profile:
                    active_intents = self.store.list_intents(profile_id)

            execution.used_profile = profile.model_dump() if profile else None
            execution.used_intents = [intent.model_dump() for intent in active_intents]

            # Get active backend and execute
            backend = self.backend_manager.get_active_backend(profile_id)
            agent_response = await backend.run_agent(
                task=request.task,
                agent_type=request.agent_type,
                profile=profile,
                active_intents=active_intents,
                metadata={"intent_ids": request.intent_ids},
            )

            response_text = agent_response.output

            # Update execution record
            end_time = _utc_now()
            execution.status = "completed"
            execution.completed_at = end_time
            execution.duration_seconds = (end_time - start_time).total_seconds()
            execution.output = response_text
            execution.metadata = agent_response.metadata

            # Save execution
            self.store.create_agent_execution(execution)

            # Record agent execution event
            try:
                event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=end_time,
                    actor=EventActor.ASSISTANT,
                    channel="api",
                    profile_id=profile_id,
                    project_id=None,  # Agent execution may not be tied to a project
                    event_type=EventType.AGENT_EXECUTION,
                    payload={
                        "execution_id": execution_id,
                        "agent_type": request.agent_type,
                        "task": request.task[:200],  # Truncate for storage
                        "status": "completed",
                        "duration_seconds": execution.duration_seconds,
                        "intent_ids": request.intent_ids,
                    },
                    entity_ids=request.intent_ids,  # Associate with intents
                    metadata={
                        "output_length": len(response_text) if response_text else 0,
                        "use_mindscape": request.use_mindscape,
                    },
                )
                self.store.create_event(event)
            except Exception as e:
                logger.warning(f"Failed to record agent execution event: {e}")

            # Extract seeds from execution (background, don't block response)
            try:
                await self._extract_seeds_from_execution(
                    profile_id=profile_id,
                    execution_id=execution_id,
                    task=request.task,
                    output=response_text,
                )
            except Exception as e:
                logger.warning(f"Failed to extract seeds: {e}")

            # Observe habits from execution (background, don't block response)
            try:
                await self._observe_habits_from_execution(
                    profile_id=profile_id, execution=execution, profile=profile
                )
            except Exception as e:
                logger.warning(f"Failed to observe habits from execution: {e}")

            return AgentResponse(
                execution_id=execution_id,
                status="completed",
                output=response_text,
                used_profile=execution.used_profile,
                used_intents=execution.used_intents,
                metadata=agent_response.metadata,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")

            end_time = _utc_now()
            execution.status = "failed"
            execution.completed_at = end_time
            execution.duration_seconds = (end_time - start_time).total_seconds()
            execution.error_message = str(e)

            self.store.create_agent_execution(execution)

            # Record failed agent execution event
            try:
                event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=end_time,
                    actor=EventActor.SYSTEM,
                    channel="api",
                    profile_id=profile_id,
                    project_id=None,
                    event_type=EventType.AGENT_EXECUTION,
                    payload={
                        "execution_id": execution_id,
                        "agent_type": request.agent_type,
                        "task": request.task[:200],
                        "status": "failed",
                        "error_message": str(e)[:500],  # Truncate error message
                        "duration_seconds": execution.duration_seconds,
                        "intent_ids": request.intent_ids,
                    },
                    entity_ids=request.intent_ids,
                    metadata={"use_mindscape": request.use_mindscape},
                )
                self.store.create_event(event)
            except Exception as e2:
                logger.warning(f"Failed to record failed agent execution event: {e2}")

            # Try to extract seeds even from failed executions (might still have useful info)
            try:
                await self._extract_seeds_from_execution(
                    profile_id=profile_id,
                    execution_id=execution_id,
                    task=request.task,
                    output=None,
                )
            except Exception as e:
                logger.warning(f"Failed to extract seeds from failed execution: {e}")

            # Try to observe habits even from failed executions (might still have useful info)
            try:
                await self._observe_habits_from_execution(
                    profile_id=profile_id, execution=execution, profile=profile
                )
            except Exception as e:
                logger.warning(f"Failed to observe habits from failed execution: {e}")

            return AgentResponse(
                execution_id=execution_id,
                status="failed",
                error_message=str(e),
                metadata={"agent_type": request.agent_type},
            )

    async def get_execution_status(self, execution_id: str) -> Optional[AgentExecution]:
        """Get execution status by ID"""
        return self.store.get_agent_execution(execution_id)

    async def list_executions(
        self, profile_id: str, limit: int = 20
    ) -> List[AgentExecution]:
        """List recent executions for a profile"""
        return self.store.list_agent_executions(profile_id, limit)

    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Get list of available agent types"""
        return [
            {
                "type": "planner",
                "name": "Project Planner",
                "description": "Helps break down goals into actionable plans",
                "category": "planning",
            },
            {
                "type": "writer",
                "name": "Content Writer",
                "description": "Creates compelling written content and visual designs",
                "category": "content_creator",
            },
            {
                "type": "coach",
                "name": "Personal Coach",
                "description": "Provides guidance and motivation",
                "category": "coaching",
            },
            {
                "type": "coder",
                "name": "Code Assistant",
                "description": "Helps with programming tasks",
                "category": "development",
            },
            {
                "type": "visual_design_partner",
                "name": "視覺設計夥伴",
                "description": "幫你把想法變成視覺素材，從社群貼文到行銷海報，自動生成多尺寸設計",
                "category": "content_creator",
                "icon": "🎨",
                "subtitle": "從文案到設計，一鍵生成多平台視覺素材",
            },
        ]

    def get_agent_detail(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific agent type, including AI team structure"""

        # Base agent information
        agents = self.get_available_agents()
        agent_info = next((a for a in agents if a["type"] == agent_type), None)

        if not agent_info:
            return None

        # Add AI team structure for specific agents
        if agent_type == "visual_design_partner":
            agent_info["ai_team"] = {
                "description": "這個成員背後有一支專業的 AI 小隊，協同完成從文案到設計的完整流程",
                "teams": [
                    {
                        "name": "內容組",
                        "members": [
                            {
                                "role": "文案生成師",
                                "capability": "content_drafting.generate",
                                "description": "從 Campaign Brief 生成標題、副標、要點等文案內容",
                            },
                            {
                                "role": "內容結構化專家",
                                "description": "將文案解析為設計元素（標題、副標、CTA）",
                            },
                        ],
                    },
                    {
                        "name": "設計組",
                        "members": [
                            {
                                "role": "模板搜尋師",
                                "tool": "canva.list_templates",
                                "description": "根據需求推薦合適的 Canva 模板",
                            },
                            {
                                "role": "設計創建師",
                                "tool": "canva.create_design_from_template",
                                "description": "從模板創建設計",
                            },
                            {
                                "role": "文字更新師",
                                "tool": "canva.update_text_blocks",
                                "description": "將文案填入設計模板",
                            },
                            {
                                "role": "多尺寸生成師",
                                "description": "自動生成 Instagram、Facebook、Banner 等多種尺寸變體",
                            },
                            {
                                "role": "資產匯出師",
                                "tool": "canva.export_design",
                                "description": "匯出最終設計檔案",
                            },
                        ],
                    },
                ],
                "workflow": [
                    "讀取 Campaign Brief（從 Intent）",
                    "生成文案內容（使用 content_drafting.generate）",
                    "解析文案為設計元素",
                    "搜尋並選擇 Canva 模板",
                    "創建設計並更新文字",
                    "生成多尺寸變體",
                    "匯出設計資產",
                ],
                "use_cases": [
                    "社群媒體貼文設計",
                    "行銷活動海報",
                    "產品宣傳素材",
                    "簡報視覺化",
                    "多平台素材批量生成",
                ],
                "related_playbooks": [
                    {
                        "code": "campaign_asset_playbook",
                        "name": "Campaign Asset Generator",
                        "description": "從 Campaign Brief 生成設計資產",
                    }
                ],
            }

        return agent_info

    def get_available_providers(self) -> List[str]:
        """Get list of available LLM providers"""
        return self.llm_manager.get_available_providers()

    async def run_agents_parallel(
        self,
        profile_id: str,
        task: str,
        agent_types: List[str],
        use_mindscape: bool = True,
        intent_ids: List[str] = None,
    ) -> List[AgentResponse]:
        """Run multiple agents in parallel for the same task"""
        if not task:
            raise ValueError("Task description required")

        # Get user context once
        profile = None
        active_intents = []

        if use_mindscape:
            profile = self.store.get_profile(profile_id)
            if profile:
                active_intents = self.store.list_intents(profile_id)

        # Get active backend
        backend = self.backend_manager.get_active_backend(profile_id)

        # Create tasks for parallel execution
        tasks = []
        for agent_type in agent_types:
            if agent_type not in ["planner", "writer", "coach", "coder"]:
                continue

            async def run_single_agent(at: str) -> AgentResponse:
                execution_id = str(uuid.uuid4())
                try:
                    agent_response = await backend.run_agent(
                        task=task,
                        agent_type=at,
                        profile=profile,
                        active_intents=active_intents,
                        metadata={
                            "intent_ids": intent_ids or [],
                            "parallel_execution": True,
                        },
                    )
                    return AgentResponse(
                        execution_id=execution_id,
                        status=agent_response.status,
                        output=agent_response.output,
                        error_message=agent_response.error_message,
                        used_profile=profile.model_dump() if profile else None,
                        used_intents=[intent.model_dump() for intent in active_intents],
                        metadata={**agent_response.metadata, "agent_type": at},
                    )
                except Exception as e:
                    logger.error(f"Parallel agent execution failed for {at}: {e}")
                    return AgentResponse(
                        execution_id=execution_id,
                        status="failed",
                        error_message=str(e),
                        metadata={"agent_type": at},
                    )

            tasks.append(run_single_agent(agent_type))

        # Execute all agents in parallel
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and convert to AgentResponse
        result = []
        for r in responses:
            if isinstance(r, Exception):
                logger.error(f"Agent execution exception: {r}")
                result.append(
                    AgentResponse(
                        execution_id=str(uuid.uuid4()),
                        status="failed",
                        error_message=str(r),
                        metadata={},
                    )
                )
            else:
                result.append(r)

        return result

    async def suggest_work_scene(self, profile_id: str, task: str) -> Dict[str, Any]:
        """Use LLM to suggest the best work scene for a given task"""
        if not task:
            raise ValueError("Task description required")

        # Get available work scenes (hardcoded for v0, can be loaded from config later)
        work_scenes = [
            {
                "id": "daily_planning",
                "name": "每日整理 & 優先級",
                "description": "整理每日/每週任務，排優先順序",
                "agent_type": "planner",
            },
            {
                "id": "project_breakdown",
                "name": "專案拆解 & 里程碑",
                "description": "將專案拆成階段和里程碑",
                "agent_type": "planner",
            },
            {
                "id": "content_drafting",
                "name": "內容／文案起稿",
                "description": "起草文案、文章、貼文",
                "agent_type": "writer",
            },
            {
                "id": "learning_plan",
                "name": "學習計畫 & 筆記整理",
                "description": "整理內容重點，制定學習計畫",
                "agent_type": "planner",
            },
            {
                "id": "mindful_dialogue",
                "name": "心智 / 情緒整理對話",
                "description": "梳理焦慮，用提問方式釐清狀態",
                "agent_type": "coach",
            },
            {
                "id": "client_collaboration",
                "name": "客戶／合作案梳理",
                "description": "整理客戶/合作案現況，列出選項",
                "agent_type": "planner",
            },
        ]

        # Build prompt for scene suggestion
        scenes_text = "\n".join(
            [
                f"- {s['id']}: {s['name']} - {s['description']} (適合: {s['agent_type']})"
                for s in work_scenes
            ]
        )

        system_prompt = f"""You are a helpful assistant that suggests the best work scenario for a user's task.

Available work scenarios:
{scenes_text}

Analyze the user's task and suggest the most appropriate work scenario.
Respond in JSON format:
{{
    "suggested_scene_id": "scene_id",
    "confidence": 0.0-1.0,
    "reason": "brief explanation in Traditional Chinese"
}}"""

        user_prompt = (
            f"Task: {task}\n\nWhich work scenario is most suitable for this task?"
        )

        try:
            # Get LLM provider from user settings
            provider = get_llm_provider_from_settings(self.llm_manager)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_text = await provider.chat_completion(messages)

            # Try to parse JSON response
            import json
            import re

            # Extract JSON from response (handle cases where LLM adds extra text)
            json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
            if json_match:
                suggestion_data = json.loads(json_match.group())
            else:
                # Fallback: try to parse the whole response
                suggestion_data = json.loads(response_text)

            # Validate and return
            suggested_id = suggestion_data.get(
                "suggested_scene_id", work_scenes[0]["id"]
            )
            scene_info = next(
                (s for s in work_scenes if s["id"] == suggested_id), work_scenes[0]
            )

            return {
                "suggested_scene_id": suggested_id,
                "suggested_scene": scene_info,
                "confidence": suggestion_data.get("confidence", 0.7),
                "reason": suggestion_data.get("reason", "根據任務內容自動推薦"),
                "all_scenes": work_scenes,
            }

        except Exception as e:
            logger.error(f"Scene suggestion failed: {e}")
            # Fallback to first scene
            return {
                "suggested_scene_id": work_scenes[0]["id"],
                "suggested_scene": work_scenes[0],
                "confidence": 0.5,
                "reason": "自動推薦失敗，使用預設場景",
                "all_scenes": work_scenes,
            }

    async def _extract_seeds_from_execution(
        self,
        profile_id: str,
        execution_id: str,
        task: str,
        output: Optional[str] = None,
    ):
        """
        Extract seeds from execution (placeholder, may be implemented later)
        This method is called but may not be fully implemented yet
        """
        # This is a placeholder - actual implementation may be in seed_extractor service
        pass

    async def _observe_habits_from_execution(
        self,
        profile_id: str,
        execution: AgentExecution,
        profile: Optional[MindscapeProfile] = None,
    ):
        """
        Observe habits from agent execution and generate candidates if threshold is met

        Args:
            profile_id: Profile ID
            execution: Agent execution record
            profile: Profile used in execution (optional)
        """
        try:
            from backend.app.capabilities.habit_learning.services.habit_observer import (
                HabitObserver,
            )
            from backend.app.capabilities.habit_learning.services.habit_candidate_generator import (
                HabitCandidateGenerator,
            )

            # Check if habit learning is enabled (from profile preferences)
            if profile and profile.preferences:
                if not getattr(profile.preferences, "enable_habit_suggestions", False):
                    logger.debug(f"Habit suggestions disabled for profile {profile_id}")
                    return

            # Create observer and generator
            observer = HabitObserver(self.store.db_path)
            generator = HabitCandidateGenerator(self.store.db_path)

            # Observe habits from execution
            observations = await observer.observe_agent_execution(
                profile_id=profile_id, execution=execution, profile=profile
            )

            # For each observation, check if we should generate a candidate
            for obs in observations:
                try:
                    generator.process_observation(
                        observation_id=obs.id,
                        profile_id=obs.profile_id,
                        habit_key=obs.habit_key,
                        habit_value=obs.habit_value,
                        habit_category=obs.habit_category,
                    )
                except Exception as e:
                    logger.warning(f"Failed to process observation {obs.id}: {e}")

        except ImportError:
            logger.debug(
                "Habit learning modules not available, skipping habit observation"
            )
        except Exception as e:
            logger.warning(
                f"Failed to observe habits from execution: {e}", exc_info=True
            )
