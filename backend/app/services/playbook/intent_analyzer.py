"""
Intent Analyzer

Uses LLM to analyze user intent and filter/rank relevant tools based on semantic understanding.
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json
import re

logger = logging.getLogger(__name__)


@dataclass
class ToolRelevanceResult:
    """Tool relevance analysis result"""
    tool_slot: str
    relevance_score: float  # 0.0-1.0
    reasoning: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0


@dataclass
class IntentAnalysisResult:
    """Intent analysis result"""
    relevant_tools: List[ToolRelevanceResult]
    overall_reasoning: Optional[str] = None
    needs_user_confirmation: bool = False


class IntentAnalyzer:
    """
    Analyzes user intent and filters/ranks relevant tools using LLM
    """

    def __init__(self, llm_provider_manager=None, profile_id=None):
        """
        Initialize Intent Analyzer

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
        min_relevance: float = 0.3
    ) -> List[Any]:
        """
        Analyze user intent and filter/rank relevant tools

        Args:
            user_message: User message
            available_tools: All available tools (List[ToolSlotInfo])
            conversation_history: Conversation history (optional)
            playbook_code: Playbook code (optional)
            max_tools: Maximum number of tools to return
            min_relevance: Minimum relevance score (0.0-1.0)

        Returns:
            Filtered and ranked tools (List[ToolSlotInfo])
        """
        # If tools are few, don't filter
        if len(available_tools) <= 5:
            logger.debug(f"Tool count ({len(available_tools)}) is low, skipping filtering")
            return available_tools

        try:
            # Analyze intent and get relevance scores
            analysis_result = await self._llm_analyze_relevance(
                user_message=user_message,
                available_tools=available_tools,
                conversation_history=conversation_history,
                playbook_code=playbook_code
            )

            # Filter tools by relevance score
            filtered_results = [
                r for r in analysis_result.relevant_tools
                if r.relevance_score >= min_relevance
            ]

            # Sort by relevance score (descending)
            filtered_results.sort(key=lambda x: x.relevance_score, reverse=True)

            # Limit to max_tools
            filtered_results = filtered_results[:max_tools]

            # Map back to ToolSlotInfo objects
            tool_slot_map = {tool.slot: tool for tool in available_tools}
            filtered_tools = []

            for result in filtered_results:
                if result.tool_slot in tool_slot_map:
                    tool = tool_slot_map[result.tool_slot]
                    # Store relevance score for sorting
                    tool.relevance_score = result.relevance_score
                    filtered_tools.append(tool)

            logger.info(f"Filtered {len(available_tools)} tools to {len(filtered_tools)} relevant tools")

            # If filtered result is too few, add fallback tools
            if len(filtered_tools) < 3 and len(available_tools) > len(filtered_tools):
                fallback_count = min(3 - len(filtered_tools), len(available_tools) - len(filtered_tools))
                remaining_tools = [t for t in available_tools if t.slot not in [ft.slot for ft in filtered_tools]]
                filtered_tools.extend(remaining_tools[:fallback_count])
                logger.debug(f"Added {fallback_count} fallback tools")

            return filtered_tools

        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}, falling back to all tools", exc_info=True)
            # Fallback: return all tools
            return available_tools

    async def _llm_analyze_relevance(
        self,
        user_message: str,
        available_tools: List[Any],
        conversation_history: Optional[List[Dict]] = None,
        playbook_code: Optional[str] = None
    ) -> IntentAnalysisResult:
        """
        Use LLM to analyze tool relevance

        Args:
            user_message: User message
            available_tools: Available tools
            conversation_history: Conversation history
            playbook_code: Playbook code

        Returns:
            IntentAnalysisResult with relevance scores
        """
        # Build conversation summary
        conversation_summary = ""
        if conversation_history:
            # Extract last few messages for context
            recent_messages = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
            conversation_summary = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
                for msg in recent_messages
            ])

        # Format tool list
        tool_list_str = self._format_tool_list(available_tools)

        # Build prompt
        prompt = f"""You are a tool selection assistant. Analyze which tools are relevant to the user's intent based on their needs.

User Message:
{user_message}

Conversation History Summary:
{conversation_summary if conversation_summary else "None"}

Available Tools List:
{tool_list_str}

Please analyze the user's intent, score the relevance of each tool (0.0-1.0), and return a list of relevant tools.

**Scoring Criteria**:
- 1.0: Perfectly matches user needs
- 0.7-0.9: Highly relevant
- 0.4-0.6: Partially relevant
- 0.0-0.3: Not relevant

Please return JSON format:
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
  "overall_reasoning": "Overall analysis"
}}
```

Return only JSON, no other text."""

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
                    return IntentAnalysisResult(relevant_tools=[])

            try:
                # Get LLM manager and provider
                profile_id = self.profile_id or "default-user"
                llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
                provider = self.llm_provider_manager.get_llm_provider(llm_manager)
            except Exception as e:
                logger.warning(f"Failed to get LLM provider: {e}, skipping intent analysis")
                return IntentAnalysisResult(relevant_tools=[])

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
            return IntentAnalysisResult(relevant_tools=[])

    def _format_tool_list(self, tools: List[Any]) -> str:
        """Format tool list for LLM prompt"""
        lines = []
        for i, tool in enumerate(tools, 1):
            tool_desc = tool.description or tool.mapped_tool_description or tool.slot
            policy_info = ""
            if tool.policy:
                policy_info = f" (risk: {tool.policy.risk_level}, env: {tool.policy.env})"

            lines.append(f"{i}. {tool.slot}")
            lines.append(f"   Description: {tool_desc}{policy_info}")
            if tool.mapped_tool_id:
                lines.append(f"   Mapped to: {tool.mapped_tool_id}")
            lines.append("")

        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> IntentAnalysisResult:
        """Parse LLM JSON response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)

                # Parse relevant tools
                relevant_tools = []
                for tool_data in data.get("relevant_tools", []):
                    relevant_tools.append(ToolRelevanceResult(
                        tool_slot=tool_data.get("tool_slot", ""),
                        relevance_score=float(tool_data.get("relevance_score", 0.0)),
                        reasoning=tool_data.get("reasoning"),
                        confidence=float(tool_data.get("confidence", 0.0))
                    ))

                return IntentAnalysisResult(
                    relevant_tools=relevant_tools,
                    overall_reasoning=data.get("overall_reasoning"),
                    needs_user_confirmation=data.get("needs_user_confirmation", False)
                )
            else:
                logger.warning("No JSON found in LLM response")
                return IntentAnalysisResult(relevant_tools=[])

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Response: {response}")
            return IntentAnalysisResult(relevant_tools=[])
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}", exc_info=True)
            return IntentAnalysisResult(relevant_tools=[])


# Global instance
_analyzer_instance: Optional[IntentAnalyzer] = None


def get_intent_analyzer(llm_provider_manager=None, profile_id=None) -> IntentAnalyzer:
    """
    Get global IntentAnalyzer instance

    Args:
        llm_provider_manager: Optional PlaybookLLMProviderManager instance
        profile_id: Optional profile ID for LLM provider

    Returns:
        IntentAnalyzer instance
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = IntentAnalyzer(llm_provider_manager=llm_provider_manager, profile_id=profile_id)
    return _analyzer_instance

