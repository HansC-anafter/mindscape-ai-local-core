"""
Summary Policy Module

Implements multi-factor policy for triggering conversation summary generation.
"""

import logging
import os
from typing import List, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class SummaryPolicy:
    """Determines when to trigger summary generation using multi-factor policy"""

    def __init__(self, store: Any = None, model_name: Optional[str] = None):
        """
        Initialize SummaryPolicy

        Args:
            store: MindscapeStore instance
            model_name: Model name for LLM calls
        """
        self.store = store
        self.model_name = model_name

    async def should_summarize(
        self,
        workspace_id: str,
        conversation_context: List[str],
        recent_events: List[Any],
    ) -> Tuple[bool, str]:
        """
        Determine if summary should be triggered using multi-factor policy

        Score = 0.5 * capacity_score + 0.3 * structure_score + 0.2 * salience_score
        Returns True if score >= 0.7

        Also checks SharedStatePolicy from Runtime Profile (Phase 2):
        - summarize_on_turn_count: Trigger summary after N turns
        - summarize_on_token_count: Trigger summary after N tokens

        Args:
            workspace_id: Workspace ID
            conversation_context: List of conversation messages
            recent_events: Recent mind events

        Returns:
            Tuple of (should_summarize, reason)
        """
        # Check SharedStatePolicy from Runtime Profile (Phase 2)
        shared_state_policy_triggered = False
        shared_state_reason = None

        try:
            from backend.app.services.stores.workspace_runtime_profile_store import (
                WorkspaceRuntimeProfileStore,
            )
            from backend.app.services.stores.workspaces_store import WorkspacesStore

            if workspace_id and self.store:
                workspaces_store = WorkspacesStore(db_path=self.store.db_path)
                workspace = await workspaces_store.get_workspace(workspace_id)

                if workspace:
                    profile_store = WorkspaceRuntimeProfileStore(
                        db_path=self.store.db_path
                    )
                    runtime_profile = profile_store.get_runtime_profile(workspace_id)

                    if runtime_profile:
                        shared_state = getattr(
                            runtime_profile, "shared_state_policy", None
                        )
                        if shared_state:
                            # Check turn count threshold
                            turn_threshold = getattr(
                                shared_state, "summarize_on_turn_count", None
                            )
                            if (
                                turn_threshold
                                and len(conversation_context) >= turn_threshold
                            ):
                                shared_state_policy_triggered = True
                                shared_state_reason = f"SharedStatePolicy: turn_count ({len(conversation_context)} >= {turn_threshold})"

                            # Check token count threshold (rough estimate)
                            if not shared_state_policy_triggered:
                                token_threshold = getattr(
                                    shared_state, "summarize_on_token_count", None
                                )
                                if token_threshold:
                                    # Rough token estimate (4 chars per token)
                                    total_chars = sum(
                                        len(msg) for msg in conversation_context
                                    )
                                    estimated_tokens = total_chars // 4
                                    if estimated_tokens >= token_threshold:
                                        shared_state_policy_triggered = True
                                        shared_state_reason = f"SharedStatePolicy: token_count ({estimated_tokens} >= {token_threshold})"

        except Exception as e:
            logger.debug(f"Failed to check SharedStatePolicy: {e}")

        if shared_state_policy_triggered:
            return True, shared_state_reason

        # Original multi-factor policy
        capacity_score = self._calculate_capacity_score(conversation_context)
        structure_score, structure_reason = await self._detect_episode_boundary(
            workspace_id, recent_events
        )
        salience_score = await self._calculate_salience_score(
            conversation_context, recent_events
        )

        # Weighted score calculation
        # Capacity: 50%, Structure: 30%, Salience: 20%
        final_score = (
            0.5 * capacity_score + 0.3 * structure_score + 0.2 * salience_score
        )

        reason_parts = []
        if capacity_score >= 0.7:
            reason_parts.append(f"capacity={capacity_score:.2f}")
        if structure_score >= 0.7:
            reason_parts.append(f"structure={structure_score:.2f} ({structure_reason})")
        if salience_score >= 0.5:
            reason_parts.append(f"salience={salience_score:.2f}")

        reason = ", ".join(reason_parts) if reason_parts else "multi-factor threshold"

        logger.info(
            f"Summary policy evaluation: capacity={capacity_score:.2f}, "
            f"structure={structure_score:.2f}, salience={salience_score:.2f}, "
            f"final={final_score:.2f}, threshold=0.7"
        )

        return final_score >= 0.7, reason

    def _calculate_capacity_score(self, conversation_context: List[str]) -> float:
        """
        Calculate capacity-based score (0~1)
        Higher score means context is approaching limit

        Args:
            conversation_context: List of conversation messages

        Returns:
            Capacity score (0~1)
        """
        if not conversation_context:
            return 0.0

        # Calculate total character count
        total_chars = sum(len(msg) for msg in conversation_context)

        # Token estimation (rough: 4 chars per token for English)
        estimated_tokens = total_chars // 4

        # Default token limits (can be overridden by model presets)
        max_context_tokens = 8000  # Conservative default
        warning_threshold = 0.7  # Start considering summary at 70% capacity

        # Calculate capacity ratio
        capacity_ratio = estimated_tokens / max_context_tokens

        # Score mapping:
        # 0-70%: 0.0 (no pressure)
        # 70-90%: 0.0-0.8 (increasing pressure)
        # 90-100%: 0.8-1.0 (high pressure)
        if capacity_ratio < warning_threshold:
            return 0.0
        elif capacity_ratio < 0.9:
            # Linear scaling from 0 to 0.8
            return (capacity_ratio - warning_threshold) / 0.2 * 0.8
        else:
            # Linear scaling from 0.8 to 1.0
            return 0.8 + (capacity_ratio - 0.9) / 0.1 * 0.2

    async def _detect_episode_boundary(
        self, workspace_id: str, recent_events: List[Any]
    ) -> Tuple[float, str]:
        """
        Detect episode boundary signals (0 or 1)

        Triggers:
        - High-level Task completed (TASK_COMPLETED with high importance)
        - Intent status transition: in_progress → paused/done
        - Plan stage finished

        Args:
            workspace_id: Workspace ID
            recent_events: Recent mind events

        Returns:
            Tuple of (score, reason)
        """
        if not recent_events:
            return 0.0, ""

        # Check last 5 events for boundary signals
        for event in recent_events[:5]:
            event_type = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )

            # Task completion signal
            if event_type == "task_completed":
                payload = event.payload if isinstance(event.payload, dict) else {}
                importance = payload.get("importance", "normal")
                if importance in ["high", "critical"]:
                    return 1.0, "high-importance task completed"

            # Intent transition signal
            if event_type == "intent_update":
                payload = event.payload if isinstance(event.payload, dict) else {}
                new_status = payload.get("new_status", "")
                old_status = payload.get("old_status", "")
                if old_status == "in_progress" and new_status in [
                    "paused",
                    "done",
                    "completed",
                ]:
                    return 1.0, f"intent transition: {old_status} → {new_status}"

            # Plan stage completion
            if event_type == "plan_stage_completed":
                return 0.8, "plan stage completed"

        return 0.0, ""

    async def _calculate_salience_score(
        self, conversation_context: List[str], recent_events: List[Any]
    ) -> float:
        """
        Calculate salience score based on importance indicators (0~1)

        Indicators:
        - Stable preferences (writing style, work habits)
        - Persistent settings (course goals, learner profiles)
        - Key decisions ("we'll use option B")

        Args:
            conversation_context: List of conversation messages
            recent_events: Recent mind events

        Returns:
            Salience score (0~1)
        """
        if not conversation_context:
            return 0.0

        # Check recent messages for importance indicators
        recent_text = "\n".join(conversation_context[-10:])  # Last 10 messages
        recent_text_lower = recent_text.lower()

        importance_keywords = [
            "decided",
            "decide to use",
            "use this",
            "fixed",
            "always",
            "final version",
            "preference",
            "always",
            "never",
            "decided",
            "final",
            "permanent",
        ]

        keyword_count = sum(
            1 for keyword in importance_keywords if keyword in recent_text_lower
        )

        # Normalize to 0~1 (more keywords = higher score)
        max_keywords = 5
        salience_score = min(1.0, keyword_count / max_keywords)

        return salience_score

    async def generate_and_store_summary(
        self,
        workspace_id: str,
        messages_to_summarize: List[str],
        profile_id: Optional[str] = None,
        summary_type: str = "HISTORY_SUMMARY",
    ):
        """
        Generate summary for old conversation messages and store as event

        Args:
            workspace_id: Workspace ID
            messages_to_summarize: List of message strings to summarize
            profile_id: Profile ID (optional)
            summary_type: Type of summary (HISTORY_SUMMARY or EPISODE_SUMMARY)
        """
        try:
            from backend.app.services.agent_runner import LLMProviderManager
            from backend.app.models.mindscape import MindEvent, EventType, EventActor
            from datetime import datetime
            import uuid

            # Combine messages into a single text
            conversation_text = "\n".join(messages_to_summarize)

            # Generate summary using LLM
            from backend.app.services.config_store import ConfigStore
            from backend.app.shared.llm_provider_helper import (
                get_llm_provider_from_settings,
                create_llm_provider_manager,
            )

            config_store = ConfigStore()
            config = config_store.get_or_create_config(profile_id or "default-user")

            # Get API key from config (same as main LLM calls) or fallback to env
            openai_key = None
            if hasattr(config, "agent_backend") and hasattr(
                config.agent_backend, "openai_api_key"
            ):
                openai_key = config.agent_backend.openai_api_key
            elif isinstance(config, dict):
                openai_key = config.get("openai_api_key")

            if not openai_key:
                openai_key = os.getenv("OPENAI_API_KEY")

            llm_manager = create_llm_provider_manager(openai_key=openai_key)
            provider = get_llm_provider_from_settings(llm_manager)

            if not provider:
                raise ValueError("OpenAI API key is not configured or is invalid")

            summary_prompt = f"""Please generate a concise summary of the following conversation history, focusing on:
1. User's main goals and needs
2. Completed progress and outcomes
3. Pending issues or next steps

Conversation history:
{conversation_text[:5000]}  # Limit to 5000 chars for summary generation

Please generate the summary in English, keep it within 300 words."""

            # Use chat_completion with messages format
            messages = [
                {
                    "role": "system",
                    "content": "You are a professional conversation summarization assistant, skilled at extracting key information and progress.",
                },
                {"role": "user", "content": summary_prompt},
            ]

            # Model must be configured - no fallback allowed
            if not self.model_name or self.model_name.strip() == "":
                raise ValueError(
                    "LLM model not configured. Please select a model in the system settings panel."
                )

            summary_text = await provider.chat_completion(
                messages=messages,
                model=self.model_name,
                max_tokens=500,
                temperature=0.3,
            )

            summary_text = summary_text.strip() if summary_text else ""

            if not summary_text or len(summary_text) < 50:
                logger.warning("Generated summary is too short, skipping storage")
                return

            # Create summary event
            summary_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                actor=EventActor.SYSTEM,
                channel="workspace",
                profile_id=profile_id or "default-user",
                workspace_id=workspace_id,
                event_type=EventType.INSIGHT,  # Use INSIGHT type for summary
                payload={
                    "summary": summary_text,
                    "content": summary_text,
                    "message_count": len(messages_to_summarize),
                    "auto_generated": True,
                    "summary_type": summary_type,
                },
                metadata={"is_summary": True, "summary_type": summary_type.lower()},
            )

            # Store the event with embedding generation
            self.store.create_event(summary_event, generate_embedding=True)
            logger.info(
                f"Stored auto-generated summary event with embedding for workspace {workspace_id}"
            )

        except Exception as e:
            logger.error(f"Failed to generate and store summary: {e}", exc_info=True)
            raise
