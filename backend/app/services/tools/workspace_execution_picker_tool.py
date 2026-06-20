"""Execution selection tool for workspace candidates."""

from typing import Any, Dict, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)
from backend.app.services.tools.workspace_tools_core import (
    select_recent_candidates,
    utc_now,
)


class WorkspacePickRelevantExecutionTool(MindscapeTool):
    """Pick the most relevant execution from candidates"""

    def __init__(self):
        metadata = ToolMetadata(
            name="workspace_pick_relevant_execution",
            description="Pick the most relevant execution from candidates using heuristics and LLM",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of candidate executions",
                    },
                    "user_query": {
                        "type": "string",
                        "description": "User's query message",
                    },
                    "conversation_context": {
                        "type": "string",
                        "description": "Conversation context",
                    },
                    "extracted_intent": {
                        "type": "object",
                        "description": "Extracted intent from user message",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace ID used to route LLM disambiguation through the preferred executor runtime",
                    },
                    "executor_runtime": {
                        "type": "string",
                        "description": "Optional executor runtime override for LLM disambiguation",
                    },
                },
                required=["candidates", "user_query"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        candidates: List[Dict[str, Any]],
        user_query: str,
        conversation_context: str = "",
        extracted_intent: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        executor_runtime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Pick the most relevant execution from candidates

        Heuristics (applied before LLM):
        1. Filter by playbook_code if extracted_intent has it
        2. Same conversation thread (recently started) - highest priority
        3. Same playbook_code, most recent - second priority
        4. If still multiple candidates, use LLM to disambiguate
        """
        if not candidates:
            raise ValueError("No candidate executions found")

        if len(candidates) == 1:
            return {
                "execution_id": candidates[0].get("execution_id")
                or candidates[0].get("id")
            }

        extracted_intent = extracted_intent or {}

        filtered_candidates = candidates
        if extracted_intent.get("playbook_code"):
            filtered_candidates = [
                c
                for c in candidates
                if c.get("playbook_code") == extracted_intent["playbook_code"]
            ]
            if len(filtered_candidates) == 1:
                return {
                    "execution_id": filtered_candidates[0].get("execution_id")
                    or filtered_candidates[0].get("id")
                }
            if len(filtered_candidates) > 1:
                candidates = filtered_candidates

        recent_candidates = select_recent_candidates(candidates, now=utc_now())

        if len(recent_candidates) == 1:
            return {
                "execution_id": recent_candidates[0].get("execution_id")
                or recent_candidates[0].get("id")
            }
        if len(recent_candidates) > 1:
            candidates = recent_candidates

        if len(candidates) == 1:
            return {
                "execution_id": candidates[0].get("execution_id")
                or candidates[0].get("id")
            }

        from backend.app.services.llm.core_llm import core_llm_call

        candidate_summary = "\n".join(
            [
                f"{i+1}. Execution {c.get('execution_id') or c.get('id', 'unknown')}: {c.get('playbook_code', 'unknown')} "
                f"(status: {c.get('status', 'unknown')}, started: {c.get('created_at', 'unknown')})"
                for i, c in enumerate(candidates[:5])
            ]
        )

        prompt = f"""
From the following candidate executions, select the one that best matches the user query:

User query: {user_query}
Conversation context: {conversation_context}
Extracted intent: {extracted_intent}

Candidates (filtered):
{candidate_summary}

Select the best matching execution_id and explain why.
"""

        result = await core_llm_call(
            user_message=prompt,
            response_format="json",
            workspace_id=workspace_id,
            executor_runtime=executor_runtime,
            stage_name="execution_selection",
            purpose="workspace_tool_execution_selection",
        )
        return {"execution_id": result["execution_id"]}
