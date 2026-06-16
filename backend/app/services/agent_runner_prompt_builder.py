"""Prompt builder for the agent runner facade."""

import logging
from typing import Any, List, Optional

from backend.app.models.mindscape import IntentCard, MindscapeProfile

logger = logging.getLogger(__name__)


class AgentPromptBuilder:
    """Builds prompts for different agent types."""

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
        """Build system prompt with user context and language policy."""

        agent_config = self.agent_prompts.get(agent_type, self.agent_prompts["planner"])

        prompt_parts = []
        prompt_parts.append(f"[AGENT_ROLE]\n{agent_config['role']}")
        prompt_parts.append(f"{agent_config['instructions']}\n[/AGENT_ROLE]")

        from backend.app.shared.i18n_loader import get_locale_from_context
        from backend.app.shared.prompt_templates import build_language_policy_section

        preferred_language = get_locale_from_context(
            profile=profile, workspace=workspace
        )
        language_policy = build_language_policy_section(preferred_language)
        prompt_parts.append(language_policy)

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
                prompt_parts.append(f"Language: {prefs.language}")
            prompt_parts.append("[/USER_PROFILE]")

        if profile:
            try:
                from backend.app.services.habit_store import HabitStore

                habit_store = HabitStore()
                confirmed_habits = habit_store.get_confirmed_habits(profile.id)

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

                if tool_preferences or playbook_preferences or agent_type_preferences:
                    prompt_parts.append("[USER_HABITS]")
                    if agent_type_preferences:
                        most_common_agent = max(
                            set(agent_type_preferences),
                            key=agent_type_preferences.count,
                        )
                        if most_common_agent == agent_type:
                            prompt_parts.append(
                                f"Note: User frequently uses {agent_type} agent type."
                            )
                    if tool_preferences:
                        common_tools = list(set(tool_preferences))[:5]
                        prompt_parts.append(
                            f"Preferred tools: {', '.join(common_tools)}"
                        )
                    if playbook_preferences:
                        common_playbooks = list(set(playbook_preferences))[:3]
                        prompt_parts.append(
                            f"Frequently used playbooks: {', '.join(common_playbooks)}"
                        )
                    prompt_parts.append("[/USER_HABITS]")
            except Exception as exc:
                logger.debug("Failed to load confirmed habits for prompt: %s", exc)

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
