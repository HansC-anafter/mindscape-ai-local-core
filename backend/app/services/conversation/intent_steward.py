"""
Intent Steward Service

Analyzes conversation turns and generates IntentLayoutPlan.
Collects IntentSignals, filters and analyzes them, then generates layout plans.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from ...models.mindscape import (
    IntentSignal, IntentLayoutPlan, IntentStewardInput,
    IntentOperation, EphemeralTask, SignalMapping,
    IntentCard, IntentTag, IntentTagStatus, IntentSource
)
from ...services.mindscape_store import MindscapeStore
from ...services.stores.intent_tags_store import IntentTagsStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...services.stores.events_store import EventsStore

logger = logging.getLogger(__name__)


class IntentStewardService:
    """
    Intent Steward Service

    Analyzes conversation turns and generates IntentLayoutPlan.
    """

    # Constraints
    MAX_CREATE_INTENT_CARDS = 3
    MAX_UPDATE_INTENT_CARDS = 5
    MIN_CONFIDENCE_THRESHOLD = 0.7
    MAX_PREFILTERED_SIGNALS = 20

    def __init__(
        self,
        store: MindscapeStore,
        default_locale: str = "en"
    ):
        """
        Initialize Intent Steward Service

        Args:
            store: MindscapeStore instance
            default_locale: Default locale for i18n
        """
        self.store = store
        self.default_locale = default_locale
        self.intent_tags_store = IntentTagsStore(db_path=store.db_path)
        self.timeline_items_store = TimelineItemsStore(db_path=store.db_path)
        self.events_store = EventsStore(db_path=store.db_path)

    async def analyze_turn(
        self,
        workspace_id: str,
        profile_id: str,
        turn_id: str,
        conversation_id: Optional[str] = None
    ) -> IntentLayoutPlan:
        """
        Analyze a conversation turn and generate IntentLayoutPlan

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            turn_id: Turn ID (usually message_id)
            conversation_id: Optional conversation ID

        Returns:
            IntentLayoutPlan: Planned changes to Intent panel
        """
        try:
            logger.info(
                f"IntentSteward: Starting analysis for turn {turn_id}, "
                f"workspace={workspace_id}, profile={profile_id}"
            )

            steward_input = await self._collect_input_data(
                workspace_id=workspace_id,
                profile_id=profile_id,
                turn_id=turn_id
            )

            filtered_signals = await self.prefilter_signals(steward_input.recent_signals)

            layout_plan = await self.steward_analyze(
                filtered_signals=filtered_signals,
                context=steward_input
            )

            layout_plan.metadata.update({
                "turn_id": turn_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "conversation_id": conversation_id,
                "steward_version": "v2_phase1",
                "timestamp": _utc_now().isoformat(),
                "mode": "observation"
            })

            auto_layout_enabled = await self._check_auto_layout_flag(profile_id, workspace_id)

            if auto_layout_enabled:
                await self._execute_layout_plan(layout_plan, workspace_id, profile_id, turn_id)
                layout_plan.metadata["executed"] = True
                layout_plan.metadata["mode"] = "execution"
            else:
                layout_plan.metadata["executed"] = False
                layout_plan.metadata["mode"] = "observation"

            await self._write_analysis_log(layout_plan, workspace_id, profile_id, turn_id)

            logger.info(
                f"IntentSteward: Analysis complete for turn {turn_id}, "
                f"planned {len(layout_plan.long_term_intents)} intent operations, "
                f"{len(layout_plan.ephemeral_tasks)} ephemeral tasks, "
                f"executed={auto_layout_enabled}"
            )

            return layout_plan

        except Exception as e:
            logger.error(f"IntentSteward: Failed to analyze turn {turn_id}: {e}", exc_info=True)
            # Return empty plan on error
            return IntentLayoutPlan(
                metadata={
                    "turn_id": turn_id,
                    "workspace_id": workspace_id,
                    "profile_id": profile_id,
                    "error": str(e),
                    "timestamp": _utc_now().isoformat()
                }
            )

    async def _collect_input_data(
        self,
        workspace_id: str,
        profile_id: str,
        turn_id: str
    ) -> IntentStewardInput:
        """
        Collect input data for IntentSteward analysis

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            turn_id: Turn ID

        Returns:
            IntentStewardInput: Collected input data
        """
        # Collect recent messages (last 10 messages)
        recent_messages = []
        try:
            events = self.events_store.list_events(
                workspace_id=workspace_id,
                limit=10,
                event_types=["message", "tool_call", "playbook_execution"]
            )
            recent_messages = [
                {
                    "id": event.id,
                    "type": event.type,
                    "content": event.content or "",
                    "metadata": event.metadata or {},
                    "created_at": event.created_at.isoformat() if event.created_at else None
                }
                for event in events
            ]
        except Exception as e:
            logger.warning(f"Failed to collect recent messages: {e}")

        # Collect recent IntentSignals (from IntentTags with CANDIDATE status)
        recent_signals = []
        try:
            # Get IntentTags from last 24 hours
            intent_tags = self.intent_tags_store.list_intent_tags(
                workspace_id=workspace_id,
                profile_id=profile_id,
                status=IntentTagStatus.CANDIDATE,
                limit=50
            )

            # Convert to IntentSignals
            for tag in intent_tags:
                signal = IntentSignal(
                    id=tag.id,
                    workspace_id=tag.workspace_id,
                    profile_id=tag.profile_id,
                    label=tag.label,
                    confidence=tag.confidence or 0.5,
                    status=tag.status.value,
                    source=tag.source.value if isinstance(tag.source, IntentSource) else str(tag.source),
                    signal_type="intent",
                    message_id=tag.message_id,
                    metadata=tag.metadata or {},
                    created_at=tag.created_at
                )
                recent_signals.append(signal)
        except Exception as e:
            logger.warning(f"Failed to collect recent signals: {e}")

        # Collect current visible IntentCards (ACTIVE / HIGH priority, ≤10)
        current_intent_cards = []
        try:
            all_intents = self.store.list_intents(profile_id=profile_id)
            # Filter: ACTIVE status and HIGH/MEDIUM priority, limit to 10
            current_intent_cards = [
                intent for intent in all_intents
                if intent.status.value == "active" and intent.priority.value in ["high", "medium"]
            ][:10]
        except Exception as e:
            logger.warning(f"Failed to collect current intent cards: {e}")

        return IntentStewardInput(
            recent_messages=recent_messages,
            recent_signals=recent_signals,
            current_intent_cards=current_intent_cards
        )

    async def prefilter_signals(
        self,
        signals: List[IntentSignal]
    ) -> List[IntentSignal]:
        """
        Prefilter signals using heuristics and small model

        Rules:
        - Only high confidence signals (≥0.7)
        - Dedupe completely identical strings in same turn
        - Filter obvious noise (too short, meaningless)

        Args:
            signals: List of IntentSignals

        Returns:
            Filtered list of IntentSignals (10-20 candidates)
        """
        if not signals:
            return []

        high_confidence = [
            s for s in signals
            if s.confidence and s.confidence >= self.MIN_CONFIDENCE_THRESHOLD
        ]

        if not high_confidence:
            return []

        seen_labels = {}
        deduped = []
        for signal in high_confidence:
            label_key = signal.label.strip().lower()
            if label_key not in seen_labels:
                seen_labels[label_key] = True
                deduped.append(signal)

        filtered = []
        for signal in deduped:
            label = signal.label.strip()
            label_clean = label.replace(" ", "").replace("\n", "")

            if (len(label) >= 3 and len(label) <= 200 and
                not label_clean.isdigit() and label_clean):
                filtered.append(signal)

                if len(filtered) >= self.MAX_PREFILTERED_SIGNALS:
                    break

        logger.info(
            f"IntentSteward: Prefiltered {len(signals)} signals -> {len(filtered)} candidates"
        )

        return filtered

    async def steward_analyze(
        self,
        filtered_signals: List[IntentSignal],
        context: IntentStewardInput
    ) -> IntentLayoutPlan:
        """
        Analyze filtered signals with LLM and generate IntentLayoutPlan

        Args:
            filtered_signals: Prefiltered IntentSignals
            context: IntentStewardInput context

        Returns:
            IntentLayoutPlan: Planned changes
        """
        layout_plan = IntentLayoutPlan()

        if not filtered_signals:
            return layout_plan

        try:
            llm_plan = await self._llm_analyze_signals(filtered_signals, context)
            if llm_plan and (llm_plan.long_term_intents or llm_plan.ephemeral_tasks):
                return llm_plan
        except Exception as e:
            logger.warning(f"LLM analysis failed, falling back to rule-based: {e}")

        # Rule-based analysis
        # Group signals by similarity (simple: exact match on first 20 chars)
        signal_groups: Dict[str, List[IntentSignal]] = {}
        for signal in filtered_signals:
            key = signal.label[:20].lower().strip()
            if key not in signal_groups:
                signal_groups[key] = []
            signal_groups[key].append(signal)

        # For each group, decide: upgrade to IntentCard or ephemeral
        for group_key, group_signals in signal_groups.items():
            if len(group_signals) == 0:
                continue

            # Use the signal with highest confidence as representative
            representative = max(group_signals, key=lambda s: s.confidence)

            # Simple heuristic: if confidence >= 0.8 and appears multiple times, upgrade
            if representative.confidence >= 0.8 and len(group_signals) >= 2:
                # Check if similar IntentCard already exists
                existing_intent = self._find_similar_intent(
                    representative.label,
                    context.current_intent_cards
                )

                if existing_intent:
                    # Update existing IntentCard
                    if len(layout_plan.long_term_intents) < self.MAX_UPDATE_INTENT_CARDS:
                        operation = IntentOperation(
                            operation_type="UPDATE_INTENT_CARD",
                            intent_id=existing_intent.id,
                            intent_data={
                                "title": existing_intent.title,
                                "description": existing_intent.description or "",
                                "priority": existing_intent.priority.value,
                                "status": existing_intent.status.value
                            },
                            relation_signals=[s.id for s in group_signals],
                            confidence=representative.confidence,
                            reasoning=f"High confidence signal ({representative.confidence:.2f}) "
                                     f"with multiple occurrences ({len(group_signals)}) "
                                     f"matches existing IntentCard"
                        )
                        layout_plan.long_term_intents.append(operation)
                else:
                    # Create new IntentCard
                    if len(layout_plan.long_term_intents) < self.MAX_CREATE_INTENT_CARDS:
                        operation = IntentOperation(
                            operation_type="CREATE_INTENT_CARD",
                            intent_id=None,
                            intent_data={
                                "title": representative.label,
                                "description": f"Auto-detected from {len(group_signals)} signals",
                                "priority": "medium",
                                "status": "active"
                            },
                            relation_signals=[s.id for s in group_signals],
                            confidence=representative.confidence,
                            reasoning=f"High confidence signal ({representative.confidence:.2f}) "
                                     f"with multiple occurrences ({len(group_signals)}) "
                                     f"warrants IntentCard creation"
                        )
                        layout_plan.long_term_intents.append(operation)
            else:
                # Ephemeral task
                task = EphemeralTask(
                    signal_id=representative.id,
                    title=representative.label,
                    description=None,
                    reasoning=f"Signal confidence {representative.confidence:.2f} or "
                             f"occurrence count {len(group_signals)} below threshold"
                )
                layout_plan.ephemeral_tasks.append(task)

            # Create signal mappings
            for signal in group_signals:
                mapping = SignalMapping(
                    signal_id=signal.id,
                    action="mapped_to_intent_id" if len(group_signals) >= 2 and representative.confidence >= 0.8 else "ignored",
                    target_intent_id=None,  # Will be set when IntentCard is created
                    reasoning=f"Grouped with {len(group_signals)} similar signals"
                )
                layout_plan.signal_mapping.append(mapping)

        return layout_plan

    async def _llm_analyze_signals(
        self,
        filtered_signals: List[IntentSignal],
        context: IntentStewardInput
    ) -> Optional[IntentLayoutPlan]:
        """
        Analyze signals using LLM

        Args:
            filtered_signals: Prefiltered IntentSignals
            context: IntentStewardInput context

        Returns:
            IntentLayoutPlan or None if LLM call fails
        """
        try:
            from ...shared.llm_utils import build_prompt, call_llm
            from ...shared.llm_provider_helper import get_llm_provider_from_settings
            from ...services.system_settings_store import SystemSettingsStore
            import json

            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")

            if not chat_setting or not chat_setting.value:
                logger.warning("No chat model configured for LLM analysis")
                return None

            model_name = str(chat_setting.value)

            from ...shared.llm_provider_helper import create_llm_provider_manager

            llm_manager = create_llm_provider_manager()

            try:
                llm_provider = get_llm_provider_from_settings(llm_manager)
            except Exception as e:
                logger.warning(f"Could not get LLM provider: {e}")
                return None

            signals_text = "\n".join([
                f"- {i+1}. {sig.label} (confidence: {sig.confidence:.2f})"
                for i, sig in enumerate(filtered_signals[:10])
            ])

            current_intents_text = "\n".join([
                f"- {intent.title} ({intent.status.value}, {intent.priority.value})"
                for intent in context.current_intent_cards[:5]
            ]) if context.current_intent_cards else "None"

            system_prompt = """You are an Intent Steward AI that analyzes user intent signals and decides which should become long-term IntentCards.

Rules:
- CREATE_INTENT_CARD: For signals that represent long-term goals or projects (confidence >= 0.75, appears important)
- UPDATE_INTENT_CARD: For signals that relate to existing IntentCards
- Ephemeral: For short-term tasks or low-priority items

Return JSON with this structure:
{
  "operations": [
    {
      "type": "CREATE_INTENT_CARD" or "UPDATE_INTENT_CARD",
      "intent_id": "existing_id" (only for UPDATE),
      "title": "Intent title",
      "description": "Brief description",
      "priority": "high" or "medium" or "low",
      "status": "active",
      "confidence": 0.0-1.0,
      "reasoning": "Why this decision"
    }
  ],
  "ephemeral": [
    {
      "title": "Task title",
      "reasoning": "Why ephemeral"
    }
  ]
}

Limit: Maximum 3 CREATE operations, 5 UPDATE operations."""

            user_prompt = f"""Analyze these intent signals:

Signals:
{signals_text}

Current IntentCards:
{current_intents_text}

Determine which signals should become IntentCards (CREATE or UPDATE) and which are ephemeral tasks.
Return only valid JSON, no additional text."""

            messages = build_prompt(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            response = await call_llm(
                messages=messages,
                llm_provider=llm_provider,
                model=model_name,
                temperature=0.3,
                max_tokens=2000
            )

            content = response.get("content", "").strip()

            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end]

            result = json.loads(content)

            layout_plan = IntentLayoutPlan()

            for op_data in result.get("operations", [])[:self.MAX_CREATE_INTENT_CARDS + self.MAX_UPDATE_INTENT_CARDS]:
                op_type = op_data.get("type", "")
                if op_type == "CREATE_INTENT_CARD":
                    if len(layout_plan.long_term_intents) < self.MAX_CREATE_INTENT_CARDS:
                        operation = IntentOperation(
                            operation_type="CREATE_INTENT_CARD",
                            intent_id=None,
                            intent_data={
                                "title": op_data.get("title", ""),
                                "description": op_data.get("description", ""),
                                "priority": op_data.get("priority", "medium"),
                                "status": op_data.get("status", "active")
                            },
                            relation_signals=[sig.id for sig in filtered_signals[:3]],
                            confidence=op_data.get("confidence", 0.7),
                            reasoning=op_data.get("reasoning", "")
                        )
                        layout_plan.long_term_intents.append(operation)
                elif op_type == "UPDATE_INTENT_CARD":
                    if len(layout_plan.long_term_intents) < self.MAX_CREATE_INTENT_CARDS + self.MAX_UPDATE_INTENT_CARDS:
                        existing_intent = self._find_similar_intent(
                            op_data.get("title", ""),
                            context.current_intent_cards
                        )
                        if existing_intent:
                            operation = IntentOperation(
                                operation_type="UPDATE_INTENT_CARD",
                                intent_id=existing_intent.id,
                                intent_data={
                                    "title": op_data.get("title", existing_intent.title),
                                    "description": op_data.get("description", existing_intent.description or ""),
                                    "priority": op_data.get("priority", existing_intent.priority.value),
                                    "status": op_data.get("status", existing_intent.status.value)
                                },
                                relation_signals=[sig.id for sig in filtered_signals[:3]],
                                confidence=op_data.get("confidence", 0.7),
                                reasoning=op_data.get("reasoning", "")
                            )
                            layout_plan.long_term_intents.append(operation)

            for ephem_data in result.get("ephemeral", [])[:10]:
                task = EphemeralTask(
                    signal_id=filtered_signals[0].id if filtered_signals else "",
                    title=ephem_data.get("title", ""),
                    description=None,
                    reasoning=ephem_data.get("reasoning", "")
                )
                layout_plan.ephemeral_tasks.append(task)

            logger.info(f"LLM analysis generated {len(layout_plan.long_term_intents)} operations, {len(layout_plan.ephemeral_tasks)} ephemeral tasks")
            return layout_plan

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return None

    def _find_similar_intent(
        self,
        label: str,
        existing_intents: List[IntentCard]
    ) -> Optional[IntentCard]:
        """
        Find similar existing IntentCard by label

        Args:
            label: Signal label
            existing_intents: List of existing IntentCards

        Returns:
            Similar IntentCard or None
        """
        label_lower = label.lower().strip()
        for intent in existing_intents:
            if intent.title.lower().strip() == label_lower:
                return intent
            # Simple similarity: first 20 chars match
            if intent.title.lower().strip()[:20] == label_lower[:20]:
                return intent
        return None

    async def _check_auto_layout_flag(
        self,
        profile_id: str,
        workspace_id: str
    ) -> bool:
        """
        Check if auto intent layout is enabled

        Args:
            profile_id: Profile ID
            workspace_id: Workspace ID

        Returns:
            True if auto layout is enabled
        """
        try:
            from ...services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()
            setting = settings_store.get_setting("auto_intent_layout")

            if setting and setting.value:
                # Check if value is boolean True or string "true"
                if isinstance(setting.value, bool):
                    return setting.value
                elif isinstance(setting.value, str):
                    return setting.value.lower() in ["true", "1", "yes"]

            return False
        except Exception as e:
            logger.warning(f"Failed to check auto_intent_layout flag: {e}")
            return False

    async def _execute_layout_plan(
        self,
        layout_plan: IntentLayoutPlan,
        workspace_id: str,
        profile_id: str,
        turn_id: str
    ):
        """
        Execute IntentLayoutPlan - create/update IntentCards

        Args:
            layout_plan: IntentLayoutPlan to execute
            workspace_id: Workspace ID
            profile_id: Profile ID
            turn_id: Turn ID
        """
        try:
            from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel

            executed_operations = []

            # Execute CREATE operations
            for operation in layout_plan.long_term_intents:
                if operation.operation_type == "CREATE_INTENT_CARD":
                    try:
                        intent_data = operation.intent_data
                        new_intent = IntentCard(
                            id=str(uuid.uuid4()),
                            profile_id=profile_id,
                            title=intent_data.get("title", ""),
                            description=intent_data.get("description", ""),
                            status=IntentStatus(intent_data.get("status", "active")),
                            priority=PriorityLevel(intent_data.get("priority", "medium")),
                            tags=intent_data.get("tags", []),
                            category=intent_data.get("category"),
                            progress_percentage=intent_data.get("progress_percentage", 0),
                            created_at=_utc_now(),
                            updated_at=_utc_now(),
                            started_at=None,
                            completed_at=None,
                            due_date=None,
                            parent_intent_id=None,
                            child_intent_ids=[],
                            metadata={
                                "source": "intent_steward_auto",
                                "turn_id": turn_id,
                                "workspace_id": workspace_id,
                                "steward_version": "v2_phase2",
                                "relation_signals": operation.relation_signals,
                                "confidence": operation.confidence,
                                "reasoning": operation.reasoning
                            }
                        )
                        created_intent = self.store.create_intent(new_intent)

                        # Update signal mappings with actual intent_id
                        for mapping in layout_plan.signal_mapping:
                            if mapping.signal_id in operation.relation_signals:
                                mapping.target_intent_id = created_intent.id

                        executed_operations.append({
                            "type": "CREATE",
                            "intent_id": created_intent.id,
                            "title": created_intent.title
                        })

                        logger.info(
                            f"IntentSteward: Created IntentCard {created_intent.id}: {created_intent.title}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to create IntentCard: {e}", exc_info=True)

                elif operation.operation_type == "UPDATE_INTENT_CARD":
                    try:
                        if not operation.intent_id:
                            logger.warning("UPDATE operation missing intent_id, skipping")
                            continue

                        existing_intent = self.store.get_intent(operation.intent_id)
                        if not existing_intent:
                            logger.warning(f"IntentCard {operation.intent_id} not found, skipping update")
                            continue

                        # Save original state for rollback
                        original_state = {
                            "title": existing_intent.title,
                            "description": existing_intent.description,
                            "priority": existing_intent.priority.value,
                            "status": existing_intent.status.value,
                            "metadata": existing_intent.metadata.copy() if existing_intent.metadata else {}
                        }

                        # Update intent data
                        intent_data = operation.intent_data
                        if "title" in intent_data:
                            existing_intent.title = intent_data["title"]
                        if "description" in intent_data:
                            existing_intent.description = intent_data["description"]
                        if "priority" in intent_data:
                            existing_intent.priority = PriorityLevel(intent_data["priority"])
                        if "status" in intent_data:
                            existing_intent.status = IntentStatus(intent_data["status"])

                        # Update metadata
                        if not existing_intent.metadata:
                            existing_intent.metadata = {}
                        existing_intent.metadata.update({
                            "source": "intent_steward_auto",
                            "last_steward_update": turn_id,
                            "workspace_id": workspace_id,
                            "steward_version": "v2_phase2",
                            "relation_signals": operation.relation_signals,
                            "confidence": operation.confidence,
                            "reasoning": operation.reasoning,
                            "rollback_data": original_state  # Store original state for rollback
                        })
                        existing_intent.updated_at = _utc_now()

                        # Save update using IntentsStore
                        updated_intent = self.store.intents.update_intent(existing_intent)
                        if updated_intent:
                            executed_operations.append({
                                "type": "UPDATE",
                                "intent_id": updated_intent.id,
                                "title": updated_intent.title,
                                "original_state": original_state
                            })

                            logger.info(
                                f"IntentSteward: Updated IntentCard {updated_intent.id}: {updated_intent.title}"
                            )
                        else:
                            logger.warning(f"Failed to update IntentCard {existing_intent.id}")
                    except Exception as e:
                        logger.error(f"Failed to update IntentCard: {e}", exc_info=True)

            layout_plan.metadata["executed_operations"] = executed_operations
            logger.info(
                f"IntentSteward: Executed {len(executed_operations)} operations "
                f"({sum(1 for op in executed_operations if op['type'] == 'CREATE')} creates, "
                f"{sum(1 for op in executed_operations if op['type'] == 'UPDATE')} updates)"
            )

        except Exception as e:
            logger.error(f"Failed to execute layout plan: {e}", exc_info=True)
            layout_plan.metadata["execution_error"] = str(e)

    async def _write_analysis_log(
        self,
        layout_plan: IntentLayoutPlan,
        workspace_id: str,
        profile_id: str,
        turn_id: str
    ):
        """
        Write analysis result to log

        Args:
            layout_plan: IntentLayoutPlan to log
            workspace_id: Workspace ID
            profile_id: Profile ID
            turn_id: Turn ID
        """
        try:
            from ...models.mindscape import IntentLog

            # Create IntentLog entry
            intent_log = IntentLog(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                raw_input=f"IntentSteward analysis for turn {turn_id}",
                channel="intent_steward",
                profile_id=profile_id,
                workspace_id=workspace_id,
                pipeline_steps={
                    "steward_version": "v2_phase2" if layout_plan.metadata.get("executed") else "v2_phase1",
                    "mode": layout_plan.metadata.get("mode", "observation")
                },
                final_decision={
                    "layout_plan": layout_plan.model_dump(),
                    "planned_operations": len(layout_plan.long_term_intents),
                    "ephemeral_tasks": len(layout_plan.ephemeral_tasks),
                    "signal_mappings": len(layout_plan.signal_mapping)
                },
                metadata={
                    "turn_id": turn_id,
                    "steward_phase": "phase2_execution" if layout_plan.metadata.get("executed") else "phase1_observation",
                    "executed": layout_plan.metadata.get("executed", False),
                    "executed_operations": layout_plan.metadata.get("executed_operations", [])
                }
            )

            # Write to intent_logs store
            self.store.create_intent_log(intent_log)

            # Also log to application log
            logger.info(
                f"INTENT_STEWARD_LOG: turn_id={turn_id}, workspace_id={workspace_id}, "
                f"profile_id={profile_id}, planned_operations={len(layout_plan.long_term_intents)}, "
                f"ephemeral_tasks={len(layout_plan.ephemeral_tasks)}, "
                f"timestamp={_utc_now().isoformat()}"
            )

        except Exception as e:
            logger.error(f"Failed to write IntentSteward analysis log: {e}", exc_info=True)

