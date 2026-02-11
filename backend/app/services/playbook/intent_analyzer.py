"""
Tool Candidate Selection

Tool slot candidate generation and precision ranking using LLM.
This is part of the ToolCandidateSelection stage (not IntentRouting).

Two-phase design:
- Phase 2A (Fast Recall): Don't miss possible tools (top 25), use fast model/embedding
- Phase 2B (Strong Precision): Ensure accuracy (top 8-10), use strong model (conditional escalation)
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import json
import re

from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


@dataclass
class ToolRelevanceResult:
    """Tool relevance analysis result"""
    tool_slot: str
    relevance_score: float  # 0.0-1.0
    reasoning: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0


@dataclass
class ToolSlotAnalysisResult:
    """Tool slot analysis result"""
    relevant_tools: List[ToolRelevanceResult]  # 1-3 most relevant tools
    overall_reasoning: Optional[str] = None
    needs_confirmation: bool = False  # Whether user confirmation is needed when multiple tools are suitable
    confidence: float = 0.0  # Overall confidence (0.0-1.0)
    escalation_required: bool = False  # Whether strong precision stage is required
    reasons: Optional[List[str]] = None  # Escalation reasons


class ToolSlotIntentAnalyzer:
    """
    Tool Candidate Selection: Generates and ranks tool slot candidates using LLM.

    This is the ToolCandidateSelection stage (not IntentRouting).
    Two-phase design: fast recall (don't miss) + strong precision (ensure accuracy).
    """

    def __init__(self, llm_provider_manager=None, profile_id=None):
        """
        Initialize Tool Candidate Selection analyzer

        Args:
            llm_provider_manager: PlaybookLLMProviderManager instance (optional)
            profile_id: Profile ID for LLM provider (optional)
        """
        self.llm_provider_manager = llm_provider_manager
        self.profile_id = profile_id

    async def analyze_and_filter_tools(
        self,
        user_message: str,
        available_tools: List[Any],  # List[ToolSlotInfo]
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        max_tools: int = 10,
        min_relevance: float = 0.3,
        risk_level: str = "read"
    ) -> List[Any]:
        """
        Two-phase tool candidate selection: fast recall + strong precision (conditional escalation)

        Design principle:
        - Recall (Phase 2A): Don't miss possible tools (top 25), use fast model/embedding
        - Precision (Phase 2B): Ensure accuracy (top 8-10), use strong model (conditional escalation)

        Args:
            user_message: User message
            available_tools: All available tools (List[ToolSlotInfo])
            conversation_history: Conversation history (optional)
            playbook_code: Playbook code (optional)
            max_tools: Maximum number of tools to return
            min_relevance: Minimum relevance score (0.0-1.0)
            risk_level: Risk level ("read", "write", "publish")

        Returns:
            Filtered and ranked tools (List[ToolSlotInfo])
        """
        # 0. If tools are few, don't filter
        if len(available_tools) <= 5:
            logger.debug(f"Tool count ({len(available_tools)}) is low, skipping filtering")
            return available_tools

        try:
            # 1. Phase 2A: Fast recall (Recall)
            # Goal: Don't miss possible tools (top 25)
            recall_result: ToolSlotAnalysisResult = await self._fast_recall(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                top_k=25
            )

            # 2. Determine if strong precision is needed
            escalation_required = self._should_escalate(
                recall_result=recall_result,
                risk_level=risk_level,
                user_message=user_message
            )

            if escalation_required:
                # 3. Phase 2B: Strong precision (Precision)
                # Design principle: Precision (ensure accuracy) - use strong model, conditional escalation
                # Goal: Ensure entry accuracy, compress to top 8-10
                precision_result: ToolSlotAnalysisResult = await self._strong_precision(
                    user_message=user_message,
                    candidate_tools=recall_result.relevant_tools,
                    conversation_history=conversation_history,
                    playbook_code=playbook_code,
                    risk_level=risk_level,
                    top_k=10,
                    original_tools=available_tools  # Pass original tools for reconstruction
                )
                final_tools = precision_result.relevant_tools
                logger.info(f"Two-phase analysis: recall={len(recall_result.relevant_tools)}, precision={len(final_tools)}")
            else:
                # No precision needed, use recall result directly
                final_tools = recall_result.relevant_tools[:max_tools]
                logger.info(f"Single-phase analysis (recall only): {len(final_tools)} tools")

            # 4. Sort and filter
            return self._sort_and_filter(final_tools, min_relevance, max_tools, available_tools)

        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}, falling back to all tools", exc_info=True)
            # Fallback: return all tools
            return available_tools

    def _should_escalate(
        self,
        recall_result: ToolSlotAnalysisResult,
        risk_level: str,
        user_message: str,
        workspace_id: Optional[str] = None,
        use_utility: bool = True
    ) -> bool:
        """
        Determine if strong precision stage is required

        Uses utility function if enabled, otherwise falls back to rule-based logic.

        Args:
            recall_result: Fast recall result
            risk_level: Risk level ("read", "write", "publish")
            user_message: User message
            workspace_id: Workspace ID (for utility evaluation)
            use_utility: Whether to use utility function for decision (default: True)

        Returns:
            True if escalation is required, False otherwise
        """
        # Use utility function if enabled
        if use_utility and workspace_id:
            try:
                from backend.app.core.utility.utility_evaluator import UtilityEvaluator
                from backend.app.core.utility.scoring_dimensions import RiskLevel as UtilityRiskLevel
                from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
                from backend.app.services.playbook.llm_provider_manager import PlaybookLLMProviderManager
                from backend.app.services.config_store import ConfigStore

                # Initialize utility evaluator
                evaluator = UtilityEvaluator()

                # Get model names for comparison
                if not self.llm_provider_manager:
                    config_store = ConfigStore()
                    self.llm_provider_manager = PlaybookLLMProviderManager(config_store)

                profile_id = self.profile_id or "default-user"
                llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
                registry = CapabilityProfileRegistry()

                # Get fast and strong models
                fast_model = registry.select_model(CapabilityProfile.FAST, llm_manager, profile_id=profile_id) or "gpt-3.5-turbo"
                strong_model = registry.select_model(CapabilityProfile.PRECISE, llm_manager, profile_id=profile_id) or "gpt-4o"

                # Map risk level
                utility_risk_level = None
                if risk_level:
                    risk_map = {
                        "read": UtilityRiskLevel.LOW,
                        "write": UtilityRiskLevel.HIGH,
                        "publish": UtilityRiskLevel.CRITICAL,
                    }
                    utility_risk_level = risk_map.get(risk_level)

                # Evaluate escalation using utility function
                should_escalate, fast_score, strong_score = evaluator.should_escalate_intent(
                    workspace_id=workspace_id,
                    action_type="tool_candidate_selection",
                    fast_model_name=fast_model,
                    strong_model_name=strong_model,
                    risk_level=utility_risk_level,
                    urgency="normal",
                    cost_constraint="normal",
                    estimated_tokens=1000,
                    escalation_threshold=0.1
                )

                logger.info(
                    f"Utility-based escalation decision: should_escalate={should_escalate}, "
                    f"fast_score={fast_score.total_score:.3f}, strong_score={strong_score.total_score:.3f}"
                )

                return should_escalate

            except Exception as e:
                logger.warning(f"Utility-based escalation evaluation failed: {e}, falling back to rule-based", exc_info=True)
                # Fall through to rule-based logic

        # Rule-based escalation (fallback or when utility is disabled)
        # Condition 1: Too many candidates
        if len(recall_result.relevant_tools) > 15:
            logger.debug(f"Escalation triggered: too many candidates ({len(recall_result.relevant_tools)})")
            return True

        # Condition 2: High risk level
        if risk_level in ["write", "publish"]:
            logger.debug(f"Escalation triggered: high risk level ({risk_level})")
            return True

        # Condition 3: Low confidence
        if recall_result.confidence and recall_result.confidence < 0.6:
            logger.debug(f"Escalation triggered: low confidence ({recall_result.confidence})")
            return True

        # Condition 4: Ambiguous message
        if user_message and self._is_ambiguous_message(user_message):
            logger.debug("Escalation triggered: ambiguous message")
            return True

        return False

    def _is_ambiguous_message(self, user_message: str) -> bool:
        """
        Check if user message is ambiguous

        Args:
            user_message: User message

        Returns:
            True if message is ambiguous, False otherwise
        """
        if not user_message:
            return True

        message_lower = user_message.lower().strip()

        # Very short messages are likely ambiguous
        if len(message_lower) < 10:
            return True

        # Messages with multiple action verbs might span multiple tools
        action_verbs = ["and", "also", "plus", "then", "after", "before", "while"]
        verb_count = sum(1 for verb in action_verbs if verb in message_lower)
        if verb_count >= 2:
            return True

        # Messages with question words might need clarification
        question_words = ["what", "which", "how", "when", "where", "why"]
        if any(word in message_lower for word in question_words) and len(message_lower) < 30:
            return True

        return False

    async def _fast_recall(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        top_k: int = 25
    ) -> ToolSlotAnalysisResult:
        """
        Fast recall stage (Phase 2A): Use fast model or embedding

        Design principle: Recall (don't miss) - use fast model/embedding, prefer more candidates
        Goal: Don't miss possible tools (high recall rate, top 25)
        Allow: Lower precision is acceptable, as long as nothing is missed

        Args:
            user_message: User message
            available_tools: Available tools
            conversation_history: Conversation history
            playbook_code: Playbook code
            top_k: Number of top candidates to return

        Returns:
            ToolSlotAnalysisResult with top_k candidates
        """
        # Use fast model for recall (gpt-3.5-turbo or similar)
        # For now, use existing _llm_analyze_relevance with fast model override
        # In future, can use embedding-based matching for even faster recall

        try:
            # Get fast model using capability profile system
            from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
            from backend.app.services.config_store import ConfigStore
            from backend.app.services.playbook.llm_provider_manager import PlaybookLLMProviderManager

            # Initialize LLM provider manager
            if not self.llm_provider_manager:
                config_store = ConfigStore()
                self.llm_provider_manager = PlaybookLLMProviderManager(config_store)

            # Select fast model
            registry = CapabilityProfileRegistry()
            profile_id = self.profile_id or "default-user"
            llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
            fast_profile = CapabilityProfile.FAST
            model_name = registry.select_model(fast_profile, llm_manager, profile_id=profile_id)

            # Fallback to chat_model if capability profile selection fails
            if not model_name:
                from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
                model_name = get_model_name_from_chat_model() or "gpt-3.5-turbo"
                logger.debug(f"Using chat_model fallback for fast recall: {model_name}")

            # Use existing LLM analysis but with relaxed criteria (return more tools)
            # Modify prompt to emphasize recall over precision
            result = await self._llm_analyze_relevance_with_model(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                model_name=model_name,
                emphasis="recall",  # Emphasize recall over precision
                max_tools=top_k
            )

            # Calculate overall confidence from relevance scores
            if result.relevant_tools:
                avg_score = sum(t.relevance_score for t in result.relevant_tools) / len(result.relevant_tools)
                result.confidence = avg_score
            else:
                result.confidence = 0.0

            logger.info(f"Fast recall: {len(result.relevant_tools)} candidates, confidence={result.confidence:.2f}")
            return result

        except Exception as e:
            logger.warning(f"Fast recall failed: {e}, falling back to all tools", exc_info=True)
            # Fallback: return all tools with low confidence
            return ToolSlotAnalysisResult(
                relevant_tools=[
                    ToolRelevanceResult(
                        tool_slot=tool.slot,
                        relevance_score=0.5,
                        reasoning="Fallback: fast recall failed"
                    )
                    for tool in available_tools[:top_k]
                ],
                confidence=0.3,
                escalation_required=True,
                reasons=["Fast recall failed, escalation required"]
            )

    async def _strong_precision(
        self,
        user_message: str,
        candidate_tools: List[ToolRelevanceResult],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        risk_level: str = "read",
        top_k: int = 10,
        original_tools: Optional[List[Any]] = None
    ) -> ToolSlotAnalysisResult:
        """
        Strong precision stage (Phase 2B): Use strong reasoning model

        Design principle: Precision (ensure accuracy) - use strong model, conditional escalation
        Goal: Ensure entry accuracy (high precision, top 8-10)
        Only triggered when necessary (conditional escalation)

        Args:
            user_message: User message
            candidate_tools: Candidate tools from recall stage
            conversation_history: Conversation history
            playbook_code: Playbook code
            risk_level: Risk level
            top_k: Number of top candidates to return
            original_tools: Original tool list (for reconstructing ToolSlotInfo objects)

        Returns:
            ToolSlotAnalysisResult with top_k precise tools
        """
        try:
            # Get strong model using capability profile system
            from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
            from backend.app.services.config_store import ConfigStore
            from backend.app.services.playbook.llm_provider_manager import PlaybookLLMProviderManager

            # Initialize LLM provider manager
            if not self.llm_provider_manager:
                config_store = ConfigStore()
                self.llm_provider_manager = PlaybookLLMProviderManager(config_store)

            # Select precise model (adjust based on risk level)
            registry = CapabilityProfileRegistry()
            profile_id = self.profile_id or "default-user"
            llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)

            # Use PRECISE profile for high-risk, SAFE_WRITE for write/publish
            if risk_level in ["write", "publish"]:
                precision_profile = CapabilityProfile.SAFE_WRITE
            else:
                precision_profile = CapabilityProfile.PRECISE

            model_name = registry.select_model(precision_profile, llm_manager, profile_id=profile_id)

            # Fallback to chat_model if capability profile selection fails
            if not model_name:
                from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
                model_name = get_model_name_from_chat_model() or "gpt-4"
                logger.debug(f"Using chat_model fallback for strong precision: {model_name}")

            # Use candidate tools directly in a precision-focused analysis
            result = await self._llm_analyze_relevance_with_model(
                user_message=user_message,
                available_tools=original_tools or [],  # Pass original tools if available
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                model_name=model_name,
                emphasis="precision",  # Emphasize precision over recall
                max_tools=top_k,
                candidate_tools=candidate_tools  # Pass candidate tools for precision analysis
            )

            # Calculate overall confidence from relevance scores
            if result.relevant_tools:
                avg_score = sum(t.relevance_score for t in result.relevant_tools) / len(result.relevant_tools)
                result.confidence = avg_score
            else:
                result.confidence = 0.0

            logger.info(f"Strong precision: {len(result.relevant_tools)} tools, confidence={result.confidence:.2f}")
            return result

        except Exception as e:
            logger.warning(f"Strong precision failed: {e}, falling back to recall result", exc_info=True)
            # Fallback: return top candidates from recall with adjusted confidence
            return ToolSlotAnalysisResult(
                relevant_tools=candidate_tools[:top_k],
                confidence=0.5,  # Lower confidence due to precision failure
                escalation_required=False,
                reasons=["Strong precision failed, using recall result"]
            )

    def _sort_and_filter(
        self,
        relevance_results: List[ToolRelevanceResult],
        min_relevance: float,
        max_tools: int,
        available_tools: List[Any]
    ) -> List[Any]:
        """
        Sort and filter tools based on relevance results

        Args:
            relevance_results: List of ToolRelevanceResult
            min_relevance: Minimum relevance score
            max_tools: Maximum number of tools to return
            available_tools: Original available tools list

        Returns:
            Filtered and sorted tools (List[ToolSlotInfo])
        """
        # Filter by relevance score
        filtered_results = [
            r for r in relevance_results
            if r.relevance_score >= min_relevance
        ]

        # Build tool slot map
        tool_slot_map = {tool.slot: tool for tool in available_tools}

        # Build filtered tools with both priority and relevance
        filtered_tools_with_scores = []
        for result in filtered_results:
            if result.tool_slot in tool_slot_map:
                tool = tool_slot_map[result.tool_slot]
                tool.relevance_score = result.relevance_score
                filtered_tools_with_scores.append(tool)

        # Sort by priority (desc) then relevance_score (desc)
        filtered_tools_with_scores.sort(
            key=lambda x: (x.priority, x.relevance_score or 0.0),
            reverse=True
        )

        # Limit to max_tools
        filtered_tools = filtered_tools_with_scores[:max_tools]

        # If filtered result is too few, add fallback tools (sorted by priority)
        if len(filtered_tools) < 3 and len(available_tools) > len(filtered_tools):
            used_slots = {ft.slot for ft in filtered_tools}
            remaining_tools = [t for t in available_tools if t.slot not in used_slots]
            remaining_tools.sort(key=lambda x: x.priority, reverse=True)
            fallback_count = min(3 - len(filtered_tools), len(remaining_tools))
            filtered_tools.extend(remaining_tools[:fallback_count])
            logger.debug(f"Added {fallback_count} fallback tools (priority-sorted)")

        return filtered_tools

    async def _llm_analyze_relevance_with_model(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        model_name: Optional[str] = None,
        emphasis: str = "balanced",  # "recall", "precision", or "balanced"
        max_tools: int = 10,
        candidate_tools: Optional[List[ToolRelevanceResult]] = None
    ) -> ToolSlotAnalysisResult:
        """
        Use LLM to analyze tool relevance with specific model and emphasis

        Args:
            user_message: User message
            available_tools: Available tools (empty if using candidate_tools)
            conversation_history: Conversation history
            playbook_code: Playbook code
            model_name: Model name to use
            emphasis: "recall" (return more tools), "precision" (return fewer, more accurate), or "balanced"
            max_tools: Maximum number of tools to return
            candidate_tools: Pre-filtered candidate tools (for precision stage)

        Returns:
            ToolSlotAnalysisResult with relevance scores
        """
        # Use candidate_tools if provided (precision stage)
        if candidate_tools:
            # Reconstruct tool list from candidate_tools for analysis
            # This is a simplified version - in practice, we'd need the original tool objects
            tool_list_for_analysis = available_tools  # Will use candidate_tools in prompt
        else:
            tool_list_for_analysis = available_tools

        # Build conversation summary with SOP stage context
        conversation_summary = ""
        sop_stage_context = ""

        if conversation_history:
            recent_messages = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
            conversation_summary = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                for msg in recent_messages
            ])

            conversation_text = " ".join([msg.get('content', '') for msg in recent_messages]).lower()
            if any(keyword in conversation_text for keyword in ['analyze', 'read', 'view', 'check', 'explore']):
                sop_stage_context = "Stage: Analysis/Reading phase - tools for reading/viewing content are more relevant."
            elif any(keyword in conversation_text for keyword in ['create', 'generate', 'write', 'draft', 'compose']):
                sop_stage_context = "Stage: Creation/Generation phase - tools for creating/generating content are more relevant."
            elif any(keyword in conversation_text for keyword in ['publish', 'deploy', 'update', 'apply', 'push']):
                sop_stage_context = "Stage: Publishing/Deployment phase - tools for publishing/updating are more relevant."

        if sop_stage_context:
            conversation_summary = f"{sop_stage_context}\n\n{conversation_summary}"

        # Format tool list
        if candidate_tools:
            # For precision stage, show candidate tools
            tool_list_str = self._format_candidate_tools(candidate_tools)
            tool_count_hint = f"Focus on these {len(candidate_tools)} pre-filtered candidates"
        else:
            tool_list_str = self._format_tool_list(tool_list_for_analysis)
            tool_count_hint = f"Analyze all {len(tool_list_for_analysis)} available tools"

        # Build prompt based on emphasis
        if emphasis == "recall":
            selection_strategy = f"""
**Selection Strategy (RECALL FOCUS)**:
- Return up to {max_tools} tools that might be relevant
- Prioritize not missing any potentially useful tools
- Lower precision is acceptable, but don't miss anything
- Include tools even if confidence is moderate (0.4-0.6)
"""
        elif emphasis == "precision":
            selection_strategy = f"""
**Selection Strategy (PRECISION FOCUS)**:
- Return only the {max_tools} most accurate and relevant tools
- Prioritize high confidence matches (0.7+)
- Exclude tools with low confidence or ambiguous relevance
- Focus on precision over recall
"""
        else:
            selection_strategy = f"""
**Selection Strategy (BALANCED)**:
- Return 1-{max_tools} most relevant tools
- Balance between recall and precision
- Prioritize high confidence matches
"""

        prompt = f"""You are a tool selection assistant. Analyze which tools are relevant to the user's intent.

User Message:
{user_message}

Conversation History Summary:
{conversation_summary if conversation_summary else "None"}

{tool_count_hint}:
{tool_list_str}

{selection_strategy}

Please analyze the user's intent and return:
- The most relevant tool slots (up to {max_tools} tools)
- Relevance scores (0.0-1.0) for each
- Reasoning for each tool
- Overall confidence in the analysis

**Scoring Criteria**:
- 1.0: Perfectly matches user needs
- 0.7-0.9: Highly relevant
- 0.4-0.6: Partially relevant
- 0.0-0.3: Not relevant

Return JSON format:
```json
{{
  "relevant_tools": [
    {{
      "tool_slot": "tool_slot_name",
      "relevance_score": 0.95,
      "reasoning": "Why this tool is relevant",
      "confidence": 0.9
    }}
  ],
  "overall_reasoning": "Overall analysis",
  "needs_confirmation": false,
  "confidence": 0.85
}}
```

**Important**: Return only JSON, no other text."""

        try:
            # Get LLM provider
            if not self.llm_provider_manager:
                from backend.app.services.config_store import ConfigStore
                from backend.app.services.playbook.llm_provider_manager import PlaybookLLMProviderManager
                config_store = ConfigStore()
                self.llm_provider_manager = PlaybookLLMProviderManager(config_store)

            try:
                profile_id = self.profile_id or "default-user"
                llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)

                # Use specified model_name or get from provider
                if model_name:
                    # Get provider for specified model
                    from backend.app.services.conversation.capability_profile import CapabilityProfileRegistry
                    registry = CapabilityProfileRegistry()
                    provider_name = registry._resolve_provider_for_model(model_name, profile_id, self.llm_provider_manager)
                    if provider_name:
                        try:
                            provider = llm_manager.get_provider(provider_name)
                        except Exception as e:
                            logger.debug(f"Failed to get provider {provider_name}: {e}, using default")
                            provider = self.llm_provider_manager.get_llm_provider(llm_manager)
                    else:
                        provider = self.llm_provider_manager.get_llm_provider(llm_manager)
                else:
                    provider = self.llm_provider_manager.get_llm_provider(llm_manager)
                    model_name = self.llm_provider_manager.get_model_name() or "gpt-4o-mini"
            except Exception as e:
                logger.warning(f"Failed to get LLM provider: {e}, skipping intent analysis")
                return ToolSlotAnalysisResult(relevant_tools=[])

            # Start trace node for LLM call
            trace_node_id = None
            trace_id = None
            try:
                trace_recorder = get_trace_recorder()
                # Try to get trace_id from execution context if available
                # For now, create a new trace if needed
                # In the future, this should be passed from the caller
                trace_id = trace_recorder.create_trace(
                    workspace_id="",  # Will be updated if available
                    execution_id=f"intent_{profile_id}_{int(_utc_now().timestamp())}",
                    user_id=profile_id,
                )
                trace_node_id = trace_recorder.start_node(
                    trace_id=trace_id,
                    node_type=TraceNodeType.LLM,
                    name=f"llm:intent_analysis:{emphasis}",
                    input_data={
                        "user_message": user_message[:200],
                        "model_name": model_name,
                        "emphasis": emphasis,
                        "available_tools_count": len(tool_list_for_analysis),
                    },
                    metadata={
                        "model_name": model_name,
                        "emphasis": emphasis,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to start trace node for LLM intent analysis: {e}")

            llm_start_time = _utc_now()
            try:
                # Call LLM
                messages = [
                    {"role": "system", "content": "You are a tool selection assistant specialized in analyzing tool relevance to user intent."},
                    {"role": "user", "content": prompt}
                ]

                # Call with model parameter if provider supports it
                try:
                    response = await provider.chat_completion(messages, max_tokens=2000, model=model_name)
                except TypeError:
                    # Provider might not support model parameter, try without it
                    response = await provider.chat_completion(messages, max_tokens=2000)

                llm_end_time = _utc_now()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)

                # Parse JSON response
                result = self._parse_llm_response(response)

                # End trace node for successful LLM call
                if trace_node_id and trace_id:
                    try:
                        trace_recorder = get_trace_recorder()
                        # Estimate token count (simplified)
                        input_tokens = len(prompt.split()) * 1.3
                        output_tokens = len(str(response).split()) * 1.3
                        total_tokens = int(input_tokens + output_tokens)

                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.SUCCESS,
                            output_data={
                                "relevant_tools_count": len(result.relevant_tools) if result else 0,
                                "confidence": result.confidence if result else 0.0,
                            },
                            cost_tokens=total_tokens,
                            latency_ms=latency_ms,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to end trace node for LLM intent analysis: {e}")

                return result
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
                        logger.warning(f"Failed to end trace node for failed LLM intent analysis: {e2}")

                logger.error(f"LLM analysis failed: {e}", exc_info=True)
                return ToolSlotAnalysisResult(relevant_tools=[])

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return ToolSlotAnalysisResult(relevant_tools=[])

    def _format_candidate_tools(self, candidate_tools: List[ToolRelevanceResult]) -> str:
        """Format candidate tools for LLM prompt (precision stage)"""
        lines = []
        for i, result in enumerate(candidate_tools, 1):
            lines.append(f"{i}. {result.tool_slot}")
            lines.append(f"   Previous relevance: {result.relevance_score:.2f}")
            if result.reasoning:
                lines.append(f"   Previous reasoning: {result.reasoning[:100]}")
            lines.append("")
        return "\n".join(lines)

    async def _llm_analyze_relevance(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None
    ) -> ToolSlotAnalysisResult:
        """
        Use LLM to analyze tool relevance (legacy method, uses default model)

        Args:
            user_message: User message
            available_tools: Available tools
            conversation_history: Conversation history
            playbook_code: Playbook code

        Returns:
            ToolSlotAnalysisResult with relevance scores
        """
        # Use default model (fallback to chat_model)
        return await self._llm_analyze_relevance_with_model(
            user_message=user_message,
            available_tools=available_tools,
            conversation_history=conversation_history,
            playbook_code=playbook_code,
            model_name=None,  # Will use default
            emphasis="balanced"
        )
        # Build conversation summary with SOP stage context (design requirement: derive intent from Playbook SOP stage)
        conversation_summary = ""
        sop_stage_context = ""

        # Try to extract SOP stage from conversation history or playbook context
        # This is a simplified version - full implementation would parse playbook.md SOP structure
        if conversation_history:
            # Extract last few messages for context (increased from 4 to 6 for better context)
            recent_messages = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
            conversation_summary = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                for msg in recent_messages
            ])

            # Try to infer stage from conversation patterns (simplified heuristic)
            # Full implementation should parse playbook.md SOP structure to get explicit stages
            conversation_text = " ".join([msg.get('content', '') for msg in recent_messages]).lower()
            if any(keyword in conversation_text for keyword in ['analyze', 'read', 'view', 'check', 'explore']):
                sop_stage_context = "Stage: Analysis/Reading phase - tools for reading/viewing content are more relevant."
            elif any(keyword in conversation_text for keyword in ['create', 'generate', 'write', 'draft', 'compose']):
                sop_stage_context = "Stage: Creation/Generation phase - tools for creating/generating content are more relevant."
            elif any(keyword in conversation_text for keyword in ['publish', 'deploy', 'update', 'apply', 'push']):
                sop_stage_context = "Stage: Publishing/Deployment phase - tools for publishing/updating are more relevant."

        # Combine conversation summary with SOP stage context
        if sop_stage_context:
            conversation_summary = f"{sop_stage_context}\n\n{conversation_summary}"

        # Format tool list
        tool_list_str = self._format_tool_list(available_tools)

        # Build prompt (design requirement: return 1-3 most relevant tools + needs_confirmation)
        prompt = f"""You are a tool selection assistant. Analyze which tools are relevant to the user's intent and select the 1-3 most relevant tools.

User Message:
{user_message}

Conversation History Summary:
{conversation_summary if conversation_summary else "None"}

Available Tools List (sorted by priority):
{tool_list_str}

**Selection Strategy**:
1. If only one tool clearly fits → select it directly
2. If multiple tools are suitable → select the most precise ones (1-3 tools), or indicate they can be combined
3. If uncertain → set needs_confirmation=true to ask user

Please analyze the user's intent and return:
- The most relevant tool slots (1-3 tools)
- Relevance scores (0.0-1.0) for each
- Reasoning for each tool
- Whether user confirmation is needed (if multiple tools are suitable and hard to distinguish)

**Scoring Criteria**:
- 1.0: Perfectly matches user needs
- 0.7-0.9: Highly relevant
- 0.4-0.6: Partially relevant
- 0.0-0.3: Not relevant

Return JSON format:
```json
{{
  "relevant_tools": [
    {{
      "tool_slot": "tool_slot_name",
      "relevance_score": 0.95,
      "reasoning": "Why this tool is relevant"
    }}
  ],
  "overall_reasoning": "Overall analysis",
  "needs_confirmation": false
}}
```

**Important**: Return only 1-3 most relevant tools. Return only JSON, no other text."""

        try:
            # Get LLM provider (use PlaybookLLMProviderManager if available)
            if not self.llm_provider_manager:
                try:
                    from backend.app.services.config_store import ConfigStore
                    from backend.app.services.playbook.llm_provider_manager import PlaybookLLMProviderManager
                    config_store = ConfigStore()
                    self.llm_provider_manager = PlaybookLLMProviderManager(config_store)
                except Exception as e:
                    logger.warning(f"Failed to initialize LLM provider manager: {e}, skipping intent analysis")
                    return ToolSlotAnalysisResult(relevant_tools=[])

            try:
                # Get LLM manager and provider
                profile_id = self.profile_id or "default-user"
                llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
                provider = self.llm_provider_manager.get_llm_provider(llm_manager)
            except Exception as e:
                logger.warning(f"Failed to get LLM provider: {e}, skipping intent analysis")
                return ToolSlotAnalysisResult(relevant_tools=[])

            # Call LLM
            messages = [
                {"role": "system", "content": "You are a tool selection assistant specialized in analyzing tool relevance to user intent."},
                {"role": "user", "content": prompt}
            ]

            response = await provider.chat_completion(messages, max_tokens=2000)

            # Parse JSON response
            result = self._parse_llm_response(response)

            return result

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            # Return empty result, will fallback to all tools
            return ToolSlotAnalysisResult(relevant_tools=[])

    def _format_tool_list(self, tools: List[Any]) -> str:
        """Format tool list for LLM prompt (include tags and priority for context)"""
        lines = []
        # Sort tools by priority first for display
        sorted_tools = sorted(tools, key=lambda x: x.priority, reverse=True)

        for i, tool in enumerate(sorted_tools, 1):
            tool_desc = tool.description or tool.mapped_tool_description or tool.slot
            policy_info = ""
            if tool.policy:
                policy_info = f" (risk: {tool.policy.risk_level}, env: {tool.policy.env})"

            tags_info = ""
            if tool.tags:
                tags_info = f" [tags: {', '.join(tool.tags)}]"

            lines.append(f"{i}. {tool.slot} (priority: {tool.priority})")
            lines.append(f"   Description: {tool_desc}{policy_info}{tags_info}")
            if tool.mapped_tool_id:
                lines.append(f"   Mapped to: {tool.mapped_tool_id}")
            lines.append("")

        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> ToolSlotAnalysisResult:
        """Parse LLM JSON response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)

                # Parse relevant tools (design requirement: 1-3 tools + needs_confirmation)
                relevant_tools = []
                for tool_data in data.get("relevant_tools", []):
                    relevant_tools.append(ToolRelevanceResult(
                        tool_slot=tool_data.get("tool_slot", ""),
                        relevance_score=float(tool_data.get("relevance_score", 0.0)),
                        reasoning=tool_data.get("reasoning"),
                        confidence=float(tool_data.get("confidence", 0.0))
                    ))

                # Enforce 1-3 tools limit at parsing layer (design requirement: hard limit, not just prompt reminder)
                if len(relevant_tools) > 3:
                    logger.warning(f"LLM returned {len(relevant_tools)} tools, truncating to 3 per design requirement")
                    relevant_tools = relevant_tools[:3]
                elif len(relevant_tools) == 0:
                    logger.warning("LLM returned no tools, this should not happen")
                    # Keep empty list, will fallback to all tools

                # Parse needs_confirmation (support both keys for backward compatibility during transition)
                # Design uses "needs_confirmation", but check "needs_user_confirmation" for any legacy responses
                needs_confirmation = data.get("needs_confirmation", False) or data.get("needs_user_confirmation", False)

                # Parse confidence (from overall or individual tools)
                overall_confidence = data.get("confidence", 0.0)
                if isinstance(overall_confidence, (int, float)):
                    confidence = float(overall_confidence)
                elif relevant_tools:
                    # Calculate from individual tool confidences if available
                    confidences = [t.confidence for t in relevant_tools if t.confidence > 0]
                    confidence = sum(confidences) / len(confidences) if confidences else 0.0
                else:
                    confidence = 0.0

                return ToolSlotAnalysisResult(
                    relevant_tools=relevant_tools,
                    overall_reasoning=data.get("overall_reasoning"),
                    needs_confirmation=needs_confirmation,
                    confidence=confidence
                )
            else:
                logger.warning("No JSON found in LLM response")
                return ToolSlotAnalysisResult(relevant_tools=[])

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Response: {response}")
            return ToolSlotAnalysisResult(relevant_tools=[])
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}", exc_info=True)
            return ToolSlotAnalysisResult(relevant_tools=[])


# Global instance
_analyzer_instance: Optional[ToolSlotIntentAnalyzer] = None


def get_tool_slot_intent_analyzer(llm_provider_manager=None, profile_id=None, model_name: Optional[str] = None) -> ToolSlotIntentAnalyzer:
    """
    Get global ToolSlotIntentAnalyzer instance

    Args:
        llm_provider_manager: Optional PlaybookLLMProviderManager instance
        profile_id: Optional profile ID for LLM provider
        model_name: Optional model name override

    Returns:
        ToolSlotIntentAnalyzer instance
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ToolSlotIntentAnalyzer(llm_provider_manager=llm_provider_manager, profile_id=profile_id)
    return _analyzer_instance


# Backward compatibility aliases (deprecated)
import warnings

IntentAnalysisResult = ToolSlotAnalysisResult
IntentAnalyzer = ToolSlotIntentAnalyzer


def get_intent_analyzer(llm_provider_manager=None, profile_id=None) -> ToolSlotIntentAnalyzer:
    """
    Get global IntentAnalyzer instance (deprecated)

    This function is deprecated. Use get_tool_slot_intent_analyzer() instead.

    Args:
        llm_provider_manager: Optional PlaybookLLMProviderManager instance
        profile_id: Optional profile ID for LLM provider

    Returns:
        ToolSlotIntentAnalyzer instance
    """
    warnings.warn(
        "get_intent_analyzer() is deprecated. Use get_tool_slot_intent_analyzer() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return get_tool_slot_intent_analyzer(llm_provider_manager=llm_provider_manager, profile_id=profile_id)

