"""
QA Response Generator

Generates QA responses with context injection for workspace interactions.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class QAResponseGenerator:
    """Generates QA responses with context injection"""

    def __init__(
        self,
        store: MindscapeStore,
        timeline_items_store,
        default_locale: str = "en"
    ):
        """
        Initialize QAResponseGenerator

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            default_locale: Default locale for i18n
        """
        self.store = store
        self.timeline_items_store = timeline_items_store
        self.default_locale = default_locale

    def _detect_collaboration_opportunity(self, message: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Detect if message suggests multi-AI collaboration opportunity

        Returns suggestion string if collaboration is appropriate, None otherwise
        """
        from ...services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=self.default_locale)
        message_lower = message.lower()

        collaboration_keywords = {
            'semantic_seeds': i18n.t("qa_response_generator", "keywords.semantic_seeds", default="understand,analyze,extract,theme,intent,concept,paper,article,document,comprehend").split(","),
            'daily_planning': i18n.t("qa_response_generator", "keywords.daily_planning", default="plan,schedule,arrange,priority,task,timeline,organize").split(","),
            'content_drafting': i18n.t("qa_response_generator", "keywords.content_drafting", default="write,draft,create,generate,produce,outline").split(",")
        }

        detected_capabilities = []
        for capability, keywords in collaboration_keywords.items():
            if any(keyword.strip().lower() in message_lower for keyword in keywords):
                detected_capabilities.append(capability)

        if len(detected_capabilities) >= 2:
            capability_names = {
                'semantic_seeds': i18n.t("qa_response_generator", "capability_names.semantic_seeds", default="Semantic Seeds Extraction"),
                'daily_planning': i18n.t("qa_response_generator", "capability_names.daily_planning", default="Daily Planning"),
                'content_drafting': i18n.t("qa_response_generator", "capability_names.content_drafting", default="Content Drafting")
            }
            suggested = [capability_names.get(c, c) for c in detected_capabilities]
            separator = i18n.t("qa_response_generator", "separator.and", default=", ")
            return i18n.t("qa_response_generator", "collaboration_suggestion", capabilities=separator.join(suggested), default=f"{separator.join(suggested)} can collaborate on this task")

        return None

    async def generate_response(
        self,
        workspace_id: str,
        profile_id: str,
        message: str,
        message_id: str,
        project_id: Optional[str] = None,
        workspace: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generate QA response with context

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message: User message
            message_id: Message/event ID
            project_id: Optional project ID

        Returns:
            Dict with assistant response and event
        """
        try:
            from backend.app.services.conversation.context_builder import ContextBuilder
            from ...capabilities.core_llm.services.generate import run as generate_text
            from ...services.i18n_service import get_i18n_service
            from ...services.system_settings_store import SystemSettingsStore

            i18n = get_i18n_service(default_locale=self.default_locale)

            # Get model name from system settings - must be configured by user
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")

            if not chat_setting or not chat_setting.value:
                raise ValueError(
                    "LLM model not configured. Please select a model in the system settings panel."
                )

            model_name = str(chat_setting.value)
            if not model_name or model_name.strip() == "":
                raise ValueError(
                    "LLM model is empty. Please select a valid model in the system settings panel."
                )

            logger.info(f"Using model '{model_name}' for context preset")

            context_builder = ContextBuilder(
                store=self.store,
                timeline_items_store=self.timeline_items_store,
                model_name=model_name
            )
            context = await context_builder.build_qa_context(
                workspace_id=workspace_id,
                message=message,
                profile_id=profile_id,
                workspace=workspace,
                hours=24
            )
            enhanced_prompt = context_builder.build_enhanced_prompt(
                message=message,
                context=context
            )

            logger.info(f"QA mode: Enhanced prompt with context (context length: {len(context)} chars)")

            collaboration_suggestion = self._detect_collaboration_opportunity(message, context)
            if collaboration_suggestion:
                system_suggestion = i18n.t(
                    "qa_response_generator",
                    "system_suggestion.collaboration",
                    suggestion=collaboration_suggestion,
                    default=f"[System Suggestion] This task may benefit from multi-AI collaboration: {collaboration_suggestion}. You can suggest the user to use these capabilities in your response."
                )
                enhanced_prompt += f"\n\n{system_suggestion}"

            # Get available playbooks for workspace capability awareness
            # Use PlaybookService to get all playbooks (system, capability, user)
            available_playbooks = []

            try:
                from ...services.playbook_service import PlaybookService
                playbook_service = PlaybookService(store=self.store)
                playbook_metadatas = await playbook_service.list_playbooks(
                    workspace_id=workspace_id,
                    locale=self.default_locale
                )

                for metadata in playbook_metadatas:
                    # Extract output_types from metadata
                    output_types = getattr(metadata, 'output_types', []) or []
                    if isinstance(output_types, str):
                        output_types = [output_types] if output_types else []

                    available_playbooks.append({
                        'playbook_code': metadata.playbook_code,
                        'name': metadata.name,
                        'description': metadata.description or '',
                        'tags': getattr(metadata, 'tags', []) or [],
                        'output_type': output_types[0] if output_types else None,
                        'output_types': output_types
                    })
            except Exception as e:
                logger.warning(f"Failed to load playbooks from PlaybookService: {e}", exc_info=True)

            result = await generate_text(
                prompt=enhanced_prompt,
                locale=self.default_locale,
                workspace_id=workspace_id,
                available_playbooks=available_playbooks
            )
            assistant_response = result.get(
                'text',
                i18n.t("conversation_orchestrator", "error.generate_response")
            )

            assistant_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": assistant_response,
                    "response_to": message_id
                },
                entity_ids=[],
                metadata={}
            )
            self.store.create_event(assistant_event)

            return {
                "response": assistant_response,
                "event": assistant_event
            }
        except Exception as e:
            logger.error(f"generate_text failed: {str(e)}", exc_info=True)
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)

            # Create error event so it appears in timeline
            try:
                error_event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    actor=EventActor.ASSISTANT,
                    channel="local_workspace",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_type=EventType.MESSAGE,
                    payload={
                        "message": i18n.t("qa_response_generator", "error.generation_failed", error=str(e), default=f"Sorry, an error occurred while generating response: {str(e)}"),
                        "response_to": message_id,
                        "error": True
                    },
                    entity_ids=[],
                    metadata={"error_type": "llm_generation_failed"}
                )
                self.store.create_event(error_event)
                return {
                    "response": i18n.t("qa_response_generator", "error.generation_failed", error=str(e), default=f"Sorry, an error occurred while generating response: {str(e)}"),
                    "event": error_event
                }
            except Exception as event_error:
                logger.error(f"Failed to create error event: {event_error}")
                return {
                    "response": i18n.t("qa_response_generator", "error.generation_failed", error=str(e), default=f"Sorry, an error occurred while generating response: {str(e)}"),
                    "event": None
                }
