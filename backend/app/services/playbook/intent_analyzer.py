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


import json

from backend.app.core.trace import get_trace_recorder
from backend.app.services.llm.core_llm import core_llm_call
from .intent_analyzer_core.escalation import (
    is_ambiguous_message,
    should_escalate_for_intent,
)
from .intent_analyzer_core.model_routing import resolve_intent_stage_model
from .intent_analyzer_core.prompting import build_tool_relevance_prompt
from .intent_analyzer_core.ranking import sort_and_filter_tools
from .intent_analyzer_core.trace import (
    finish_intent_trace_failure,
    finish_intent_trace_success,
    start_intent_trace,
    utc_now,
)
from .intent_analyzer_core import (
    ToolRelevanceResult,
    ToolSlotAnalysisResult,
    format_candidate_tools,
    format_tool_list,
    parse_llm_response,
)

logger = logging.getLogger(__name__)


class ToolSlotIntentAnalyzer:
    """
    Tool Candidate Selection: Generates and ranks tool slot candidates using LLM.

    This is the ToolCandidateSelection stage (not IntentRouting).
    Two-phase design: fast recall (don't miss) + strong precision (ensure accuracy).
    """

    def __init__(self, llm_provider_manager=None, profile_id=None):
        self.llm_provider_manager = llm_provider_manager
        self.profile_id = profile_id

    async def analyze_and_filter_tools(
        self,
        user_message: str,
        available_tools: List[Any],  # List[ToolSlotInfo]
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        workspace_id: Optional[str] = None,
        max_tools: int = 10,
        min_relevance: float = 0.3,
        risk_level: str = "read"
    ) -> List[Any]:
        if len(available_tools) <= 5:
            logger.debug(f"Tool count ({len(available_tools)}) is low, skipping filtering")
            return available_tools

        try:
            recall_result: ToolSlotAnalysisResult = await self._fast_recall(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                workspace_id=workspace_id,
                risk_level=risk_level,
                top_k=25
            )

            escalation_required = self._should_escalate(
                recall_result=recall_result,
                risk_level=risk_level,
                user_message=user_message,
                workspace_id=workspace_id,
            )

            if escalation_required:
                precision_result: ToolSlotAnalysisResult = await self._strong_precision(
                    user_message=user_message,
                    candidate_tools=recall_result.relevant_tools,
                    conversation_history=conversation_history,
                    playbook_code=playbook_code,
                    workspace_id=workspace_id,
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

            return self._sort_and_filter(final_tools, min_relevance, max_tools, available_tools)

        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}, falling back to all tools", exc_info=True)
            return available_tools

    def _should_escalate(
        self,
        recall_result: ToolSlotAnalysisResult,
        risk_level: str,
        user_message: str,
        workspace_id: Optional[str] = None,
        use_utility: bool = True
    ) -> bool:
        decision, self.llm_provider_manager = should_escalate_for_intent(
            recall_result=recall_result,
            risk_level=risk_level,
            user_message=user_message,
            workspace_id=workspace_id,
            llm_provider_manager=self.llm_provider_manager,
            profile_id=self.profile_id,
            logger=logger,
            use_utility=use_utility,
        )
        return decision

    def _is_ambiguous_message(self, user_message: str) -> bool:
        return is_ambiguous_message(user_message)

    async def _fast_recall(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        workspace_id: Optional[str] = None,
        risk_level: str = "read",
        top_k: int = 25
    ) -> ToolSlotAnalysisResult:
        try:
            self.llm_provider_manager, model_name = resolve_intent_stage_model(
                llm_provider_manager=self.llm_provider_manager,
                profile_id=self.profile_id,
                stage_name="intent_analysis",
                risk_level=risk_level,
            )

            result = await self._llm_analyze_relevance_with_model(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                workspace_id=workspace_id,
                model_name=model_name,
                emphasis="recall",  # Emphasize recall over precision
                max_tools=top_k,
                risk_level=risk_level,
            )

            if result.relevant_tools:
                avg_score = sum(t.relevance_score for t in result.relevant_tools) / len(result.relevant_tools)
                result.confidence = avg_score
            else:
                result.confidence = 0.0

            logger.info(f"Fast recall: {len(result.relevant_tools)} candidates, confidence={result.confidence:.2f}")
            return result

        except Exception as e:
            logger.warning(f"Fast recall failed: {e}, falling back to all tools", exc_info=True)
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
        workspace_id: Optional[str] = None,
        risk_level: str = "read",
        top_k: int = 10,
        original_tools: Optional[List[Any]] = None
    ) -> ToolSlotAnalysisResult:
        try:
            precision_stage = "scope_decision" if risk_level in ["write", "publish"] else "plan_generation"
            self.llm_provider_manager, model_name = resolve_intent_stage_model(
                llm_provider_manager=self.llm_provider_manager,
                profile_id=self.profile_id,
                stage_name=precision_stage,
                risk_level=risk_level,
            )

            result = await self._llm_analyze_relevance_with_model(
                user_message=user_message,
                available_tools=original_tools or [],  # Pass original tools if available
                conversation_history=conversation_history,
                playbook_code=playbook_code,
                workspace_id=workspace_id,
                model_name=model_name,
                emphasis="precision",  # Emphasize precision over recall
                max_tools=top_k,
                candidate_tools=candidate_tools,  # Pass candidate tools for precision analysis
                risk_level=risk_level,
            )

            if result.relevant_tools:
                avg_score = sum(t.relevance_score for t in result.relevant_tools) / len(result.relevant_tools)
                result.confidence = avg_score
            else:
                result.confidence = 0.0

            logger.info(f"Strong precision: {len(result.relevant_tools)} tools, confidence={result.confidence:.2f}")
            return result

        except Exception as e:
            logger.warning(f"Strong precision failed: {e}, falling back to recall result", exc_info=True)
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
        return sort_and_filter_tools(
            relevance_results=relevance_results,
            min_relevance=min_relevance,
            max_tools=max_tools,
            available_tools=available_tools,
            logger=logger,
        )

    async def _llm_analyze_relevance_with_model(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        workspace_id: Optional[str] = None,
        model_name: Optional[str] = None,
        emphasis: str = "balanced",  # "recall", "precision", or "balanced"
        max_tools: int = 10,
        candidate_tools: Optional[List[ToolRelevanceResult]] = None,
        risk_level: str = "read",
    ) -> ToolSlotAnalysisResult:
        try:
            profile_id = self.profile_id or "default-user"
            prompt_payload = build_tool_relevance_prompt(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                emphasis=emphasis,
                max_tools=max_tools,
                candidate_tools=candidate_tools,
            )
            trace_handle = start_intent_trace(
                recorder_factory=get_trace_recorder,
                profile_id=profile_id,
                workspace_id=workspace_id,
                user_message=user_message,
                model_name=model_name,
                emphasis=emphasis,
                available_tools_count=len(prompt_payload.tool_list_for_analysis),
                logger=logger,
            )

            llm_start_time = utc_now()
            try:
                response = await core_llm_call(
                    user_message=prompt_payload.prompt,
                    system_prompt=(
                        "You are a tool selection assistant specialized in analyzing "
                        "tool relevance to user intent."
                    ),
                    response_format="json",
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    model=model_name,
                    stage_name="intent_analysis",
                    purpose="intent_analysis.tool_relevance",
                    risk_level=risk_level,
                )

                llm_end_time = utc_now()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)

                result = self._parse_llm_payload(response)
                finish_intent_trace_success(
                    handle=trace_handle,
                    recorder_factory=get_trace_recorder,
                    prompt=prompt_payload.prompt,
                    response=response,
                    result=result,
                    latency_ms=latency_ms,
                    logger=logger,
                )

                return result
            except Exception as e:
                llm_end_time = utc_now()
                latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)
                finish_intent_trace_failure(
                    handle=trace_handle,
                    recorder_factory=get_trace_recorder,
                    error=e,
                    latency_ms=latency_ms,
                    logger=logger,
                )

                logger.error(f"LLM analysis failed: {e}", exc_info=True)
                return ToolSlotAnalysisResult(relevant_tools=[])

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return ToolSlotAnalysisResult(relevant_tools=[])

    def _format_candidate_tools(self, candidate_tools: List[ToolRelevanceResult]) -> str:
        return format_candidate_tools(candidate_tools)

    async def _llm_analyze_relevance(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> ToolSlotAnalysisResult:
        return await self._llm_analyze_relevance_with_model(
            user_message=user_message,
            available_tools=available_tools,
            conversation_history=conversation_history,
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            model_name=None,
            emphasis="balanced"
        )

    def _format_tool_list(self, tools: List[Any]) -> str:
        return format_tool_list(tools)

    def _parse_llm_response(self, response: str) -> ToolSlotAnalysisResult:
        return parse_llm_response(response)

    def _parse_llm_payload(self, response: Any) -> ToolSlotAnalysisResult:
        if isinstance(response, dict):
            return parse_llm_response(json.dumps(response))
        return self._parse_llm_response(str(response))


# Global instance
_analyzer_instance: Optional[ToolSlotIntentAnalyzer] = None


def get_tool_slot_intent_analyzer(llm_provider_manager=None, profile_id=None, model_name: Optional[str] = None) -> ToolSlotIntentAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ToolSlotIntentAnalyzer(llm_provider_manager=llm_provider_manager, profile_id=profile_id)
    return _analyzer_instance


# Backward compatibility aliases (deprecated)
import warnings

IntentAnalysisResult = ToolSlotAnalysisResult
IntentAnalyzer = ToolSlotIntentAnalyzer


def get_intent_analyzer(llm_provider_manager=None, profile_id=None) -> ToolSlotIntentAnalyzer:
    warnings.warn(
        "get_intent_analyzer() is deprecated. Use get_tool_slot_intent_analyzer() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return get_tool_slot_intent_analyzer(llm_provider_manager=llm_provider_manager, profile_id=profile_id)
