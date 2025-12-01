"""
Message Generator Service

Uses LLM to generate natural language messages for user feedback,
suggestions, and confirmations.
Also generates HandoffPlan for multi-step workflows.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from ...capabilities.core_llm.services.generate import run as llm_generate
from ...models.playbook import HandoffPlan, WorkflowStep, PlaybookKind, InteractionMode
from ...services.intent_analyzer import IntentAnalysisResult
from ...services.handoff_plan_builder import HandoffPlanBuilder

logger = logging.getLogger(__name__)


class MessageGenerator:
    """Generate natural language messages using LLM"""

    def __init__(self, llm_provider=None, default_locale: str = "en"):
        """
        Initialize MessageGenerator

        Args:
            llm_provider: LLM provider instance (optional)
            default_locale: Default locale for messages
        """
        self.llm_provider = llm_provider
        self.default_locale = default_locale

    async def generate_readonly_feedback(
        self,
        timeline_item: Dict[str, Any],
        task_result: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None
    ) -> str:
        """
        Generate natural feedback message for readonly task completion

        Args:
            timeline_item: Timeline item dict with task results
            task_result: Task execution result (optional)
            locale: Locale for message generation (optional)

        Returns:
            Natural feedback message describing what was automatically analyzed
        """
        try:
            if not self.llm_provider:
                # Fallback to i18n template if LLM not available
                summary = timeline_item.get('summary', '')
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                return i18n.t(
                    "conversation_orchestrator",
                    "feedback.readonly",
                    summary=summary or "Analysis completed"
                )

            # Extract information from timeline item
            title = timeline_item.get('title', '')
            summary = timeline_item.get('summary', '')
            item_type = timeline_item.get('type', '')
            data = timeline_item.get('data', {})

            # Build context for LLM
            context_parts = []
            if title:
                context_parts.append(f"Title: {title}")
            if summary:
                context_parts.append(f"Summary: {summary}")
            if task_result:
                result_summary = task_result.get('message') or task_result.get('summary', '')
                if result_summary:
                    context_parts.append(f"Result: {result_summary}")

            context = "\n".join(context_parts) if context_parts else "Analysis completed"

            # Generate natural feedback message
            system_prompt = """You are a helpful AI assistant providing feedback to users about completed analysis tasks.

Generate a brief, natural, and friendly feedback message that:
1. Acknowledges what was analyzed
2. Highlights key findings or results
3. Is concise (1-2 sentences)
4. Uses natural, conversational language

Do not use generic greetings or formal phrases. Be direct and helpful."""

            user_prompt = f"""The following analysis task has been completed:

{context}

Generate a natural feedback message for the user describing what was analyzed and the key findings."""

            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                llm_provider=self.llm_provider,
                target_language=locale or self.default_locale
            )

            feedback = result.get('text', '').strip()
            if feedback:
                return feedback
            else:
                # Fallback to i18n
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                return i18n.t(
                    "conversation_orchestrator",
                    "feedback.readonly",
                    summary=summary or "Analysis completed"
                )

        except Exception as e:
            logger.warning(f"Failed to generate LLM feedback: {e}, falling back to i18n template")
            # Fallback to i18n template
            summary = timeline_item.get('summary', '')
            from ...services.i18n_service import I18nService
            i18n = I18nService(default_locale=locale or self.default_locale)
            return i18n.t(
                "conversation_orchestrator",
                "feedback.readonly",
                summary=summary or "Analysis completed"
            )

    async def generate_suggestion_message(
        self,
        pack_id: str,
        task_result: Dict[str, Any],
        timeline_item: Dict[str, Any],
        locale: Optional[str] = None
    ) -> str:
        """
        Generate natural suggestion message for soft_write tasks

        Args:
            pack_id: Pack identifier
            task_result: Task execution result
            timeline_item: Timeline item with suggestion data
            locale: Locale for message generation (optional)

        Returns:
            Natural suggestion message explaining what can be added
        """
        try:
            if not self.llm_provider:
                # Fallback to i18n template
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                return i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")

            # Extract information
            title = timeline_item.get('title', '')
            summary = timeline_item.get('summary', '')
            data = timeline_item.get('data', {})
            result_summary = task_result.get('message') or task_result.get('summary', '')

            # Build context
            context = f"""Pack: {pack_id}
Title: {title}
Summary: {summary or result_summary}"""

            if data:
                # Extract key information from data
                if isinstance(data, dict):
                    key_info = []
                    if 'intents' in data:
                        intents = data.get('intents', [])
                        if isinstance(intents, list) and len(intents) > 0:
                            key_info.append(f"Found {len(intents)} intent(s)")
                    if 'tasks' in data:
                        tasks = data.get('tasks', [])
                        if isinstance(tasks, list) and len(tasks) > 0:
                            key_info.append(f"Found {len(tasks)} task(s)")
                    if key_info:
                        context += f"\nKey findings: {', '.join(key_info)}"

            # Generate natural suggestion message
            system_prompt = """You are a helpful AI assistant suggesting actions to users.

Generate a brief, natural suggestion message that:
1. Explains what was found or extracted
2. Suggests adding it to the user's workspace (intents, tasks, etc.)
3. Is friendly and encouraging
4. Is concise (1-2 sentences)

Do not use generic greetings. Be direct and helpful."""

            user_prompt = f"""The following content has been extracted:

{context}

Generate a natural suggestion message encouraging the user to add this to their workspace."""

            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                llm_provider=self.llm_provider,
                target_language=locale or self.default_locale
            )

            suggestion = result.get('text', '').strip()
            if suggestion:
                return suggestion
            else:
                # Fallback to i18n
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                return i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")

        except Exception as e:
            logger.warning(f"Failed to generate LLM suggestion: {e}, falling back to i18n template")
            # Fallback to i18n template
            from ...services.i18n_service import I18nService
            i18n = I18nService(default_locale=locale or self.default_locale)
            return i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")

    async def generate_confirmation_message(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        timeline_item: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate detailed confirmation message for external_write actions

        Args:
            action_type: Action type (e.g., 'publish_to_wordpress')
            action_params: Action parameters
            timeline_item: Timeline item with content to be published (optional)
            locale: Locale for message generation (optional)

        Returns:
            Dict with confirmation message and buttons
        """
        try:
            if not self.llm_provider:
                # Fallback to i18n template
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                return {
                    "message": i18n.t(
                        "conversation_orchestrator",
                        "confirmation.external_write",
                        action_type=action_type
                    ),
                    "confirm_buttons": [
                        {
                            "label": i18n.t("conversation_orchestrator", "confirmation.button_confirm"),
                            "action": action_type,
                            "confirm": True
                        },
                        {
                            "label": i18n.t("conversation_orchestrator", "confirmation.button_cancel"),
                            "action": "cancel"
                        }
                    ]
                }

            # Build context for confirmation
            context_parts = [f"Action: {action_type}"]

            if timeline_item:
                title = timeline_item.get('title', '')
                summary = timeline_item.get('summary', '')
                if title:
                    context_parts.append(f"Content title: {title}")
                if summary:
                    context_parts.append(f"Content summary: {summary}")

            if action_params:
                if 'title' in action_params:
                    context_parts.append(f"Title: {action_params['title']}")
                if 'url' in action_params:
                    context_parts.append(f"Target URL: {action_params['url']}")

            context = "\n".join(context_parts)

            # Generate detailed confirmation message
            system_prompt = """You are a helpful AI assistant asking for user confirmation before performing external actions.

Generate a clear, detailed confirmation message that:
1. Explains what action will be performed
2. Mentions key details (title, target, etc.)
3. Asks for explicit confirmation
4. Is professional and clear
5. Is concise but informative (2-3 sentences)

Do not use generic greetings. Be direct and clear about the action."""

            user_prompt = f"""The following external action is about to be performed:

{context}

Generate a detailed confirmation message asking the user to confirm this action."""

            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.5,  # Lower temperature for more consistent confirmations
                llm_provider=self.llm_provider,
                target_language=locale or self.default_locale
            )

            confirmation_message = result.get('text', '').strip()
            if not confirmation_message:
                # Fallback to i18n
                from ...services.i18n_service import I18nService
                i18n = I18nService(default_locale=locale or self.default_locale)
                confirmation_message = i18n.t(
                    "conversation_orchestrator",
                    "confirmation.external_write",
                    action_type=action_type
                )

            return {
                "message": confirmation_message,
                "confirm_buttons": [
                    {
                        "label": self._get_confirm_button_label(action_type, locale),
                        "action": action_type,
                        "confirm": True
                    },
                    {
                        "label": self._get_cancel_button_label(locale),
                        "action": "cancel"
                    }
                ]
            }

        except Exception as e:
            logger.warning(f"Failed to generate LLM confirmation: {e}, falling back to i18n template")
            # Fallback to i18n template
            from ...services.i18n_service import I18nService
            i18n = I18nService(default_locale=locale or self.default_locale)
            return {
                "message": i18n.t(
                    "conversation_orchestrator",
                    "confirmation.external_write",
                    action_type=action_type
                ),
                "confirm_buttons": [
                    {
                        "label": i18n.t("conversation_orchestrator", "confirmation.button_confirm"),
                        "action": action_type,
                        "confirm": True
                    },
                    {
                        "label": i18n.t("conversation_orchestrator", "confirmation.button_cancel"),
                        "action": "cancel"
                    }
                ]
            }

    def _get_confirm_button_label(self, action_type: str, locale: Optional[str] = None) -> str:
        """Get confirm button label based on action type"""
        from ...services.i18n_service import I18nService
        i18n = I18nService(default_locale=locale or self.default_locale)

        if 'wordpress' in action_type.lower() or 'publish' in action_type.lower():
            return i18n.t("conversation_orchestrator", "confirmation.button_publish", fallback="Publish")
        elif 'export' in action_type.lower():
            return i18n.t("conversation_orchestrator", "confirmation.button_export", fallback="Export")
        else:
            return i18n.t("conversation_orchestrator", "confirmation.button_confirm", fallback="Confirm")

    def _get_cancel_button_label(self, locale: Optional[str] = None) -> str:
        """Get cancel button label"""
        from ...services.i18n_service import I18nService
        i18n = I18nService(default_locale=locale or self.default_locale)
        return i18n.t("conversation_orchestrator", "confirmation.button_cancel", fallback="Cancel")

    async def generate_workflow_response(
        self,
        user_input: str,
        intent_result: IntentAnalysisResult,
        context: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate LLM response that may include HandoffPlan for multi-step workflows

        Args:
            user_input: User input text
            intent_result: IntentAnalysisResult from IntentPipeline
            context: Additional context (e.g., uploaded files)
            locale: Locale for message generation

        Returns:
            Dict with 'message' (user-friendly text) and optional 'handoff_plan'
        """
        if not self.llm_provider:
            return {
                "message": "I understand your request, but I need an LLM provider to generate a workflow plan.",
                "handoff_plan": None
            }

        if not intent_result.is_multi_step or not intent_result.workflow_steps:
            return {
                "message": await self._generate_single_step_response(
                    user_input, intent_result, context, locale
                ),
                "handoff_plan": None
            }

        handoff_plan_builder = HandoffPlanBuilder()
        context_dict = context or {}
        if intent_result.playbook_context:
            context_dict.update(intent_result.playbook_context)

        try:
            handoff_plan = handoff_plan_builder.build_handoff_plan(
                simplified_steps=intent_result.workflow_steps,
                context=context_dict,
                estimated_duration=None
            )
        except Exception as e:
            logger.warning(f"Failed to build HandoffPlan: {e}")
            return {
                "message": "I understand your request, but encountered an error planning the workflow.",
                "handoff_plan": None
            }

        system_prompt = """You are a helpful AI assistant that understands user requests and creates execution plans.

When the user requests a multi-step workflow, you should:
1. Acknowledge the request in a friendly, natural way
2. Briefly explain what steps will be executed
3. Include a HandoffPlan in <playbook_handoff>...</playbook_handoff> tags

The HandoffPlan should be valid JSON matching this structure:
{
  "steps": [
    {
      "playbook_code": "playbook_name",
      "kind": "user_workflow" or "system_tool",
      "interaction_mode": ["silent", "needs_review", or "conversational"],
      "inputs": {...},
      "input_mapping": {...}
    }
  ],
  "context": {...},
  "estimated_duration": 300
}

Be concise and natural in your response. The HandoffPlan is for the system, not the user."""

        workflow_summary = self._format_workflow_summary(handoff_plan)

        user_prompt = f"""User request: "{user_input}"

I have identified this as a multi-step workflow with the following steps:
{workflow_summary}

Generate a natural response that:
1. Acknowledges the request
2. Explains what will be done
3. Includes the complete HandoffPlan in <playbook_handoff> tags

HandoffPlan JSON:
{json.dumps(handoff_plan.dict(), indent=2, ensure_ascii=False)}"""

        try:
            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                llm_provider=self.llm_provider,
                target_language=locale or self.default_locale
            )

            response_text = result.get('text', '').strip()
            if not response_text:
                response_text = f"I'll help you with that. I've planned a workflow with {len(handoff_plan.steps)} steps."

            return {
                "message": response_text,
                "handoff_plan": handoff_plan
            }

        except Exception as e:
            logger.warning(f"Failed to generate workflow response: {e}")
            return {
                "message": f"I'll help you with that. I've planned a workflow with {len(handoff_plan.steps)} steps.",
                "handoff_plan": handoff_plan
            }

    async def _generate_single_step_response(
        self,
        user_input: str,
        intent_result: IntentAnalysisResult,
        context: Optional[Dict[str, Any]],
        locale: Optional[str]
    ) -> str:
        """Generate response for single-step requests"""
        if intent_result.selected_playbook_code:
            return f"I'll help you with that using the {intent_result.selected_playbook_code} playbook."
        return "I understand your request."

    def _format_workflow_summary(self, handoff_plan: HandoffPlan) -> str:
        """Format workflow steps as a readable summary"""
        summary_parts = []
        for i, step in enumerate(handoff_plan.steps, 1):
            kind_label = "System tool" if step.kind == PlaybookKind.SYSTEM_TOOL else "User workflow"
            summary_parts.append(f"{i}. {kind_label}: {step.playbook_code}")
        return "\n".join(summary_parts)

    async def generate_workflow_summary(
        self,
        workflow_result: Dict[str, Any],
        handoff_plan: HandoffPlan,
        locale: Optional[str] = None
    ) -> str:
        """
        Generate user-friendly summary of workflow execution results

        Args:
            workflow_result: Workflow execution result from WorkflowOrchestrator
            handoff_plan: Original HandoffPlan
            locale: Locale for message generation

        Returns:
            Natural language summary of workflow execution
        """
        if not self.llm_provider:
            from ...services.i18n_service import I18nService
            i18n = I18nService(default_locale=locale or self.default_locale)
            return i18n.t("conversation_orchestrator", "workflow.completed", fallback="Workflow completed successfully")

        steps_results = workflow_result.get('steps', {})
        completed_steps = [k for k, v in steps_results.items() if v.get('status') == 'completed']
        failed_steps = [k for k, v in steps_results.items() if v.get('status') == 'error']

        system_prompt = """You are a helpful AI assistant summarizing workflow execution results.

Generate a concise, natural summary that:
1. Acknowledges completion of the workflow
2. Highlights key results from each step
3. Mentions any errors if they occurred
4. Is friendly and informative
5. Is 2-3 sentences long

Be specific about what was accomplished."""

        workflow_summary = f"""Workflow executed with {len(handoff_plan.steps)} steps.

Completed steps: {', '.join(completed_steps) if completed_steps else 'None'}
Failed steps: {', '.join(failed_steps) if failed_steps else 'None'}

Step results:
"""
        for step_code, result in steps_results.items():
            status = result.get('status', 'unknown')
            outputs = result.get('outputs', {})
            workflow_summary += f"- {step_code}: {status}"
            if outputs:
                output_keys = list(outputs.keys())[:3]
                workflow_summary += f" (outputs: {', '.join(output_keys)})"
            workflow_summary += "\n"

        user_prompt = f"""The following workflow has been executed:

{workflow_summary}

Generate a natural summary message for the user."""

        try:
            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                llm_provider=self.llm_provider,
                target_language=locale or self.default_locale
            )

            summary = result.get('text', '').strip()
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"Failed to generate workflow summary: {e}")

        from ...services.i18n_service import I18nService
        i18n = I18nService(default_locale=locale or self.default_locale)
        return i18n.t("conversation_orchestrator", "workflow.completed", fallback="Workflow completed successfully")
