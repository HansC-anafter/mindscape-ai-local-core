"""
Multi-step workflow detection helpers for IntentPipeline.
"""

import logging
from typing import Any, Dict, Optional

from backend.app.shared.llm_utils import build_prompt, call_llm

from .utils import parse_json_from_response

logger = logging.getLogger(__name__)


async def detect_multi_step_workflow(
    user_input: str,
    initial_playbook_code: str,
    context: Dict[str, Any],
    llm_provider: Any,
    playbook_service: Any,
) -> Optional[Dict[str, Any]]:
    """
    Detect whether a selected playbook should expand into multiple workflow steps.

    Args:
        user_input: User input text
        initial_playbook_code: Initially selected playbook
        context: Playbook context
        llm_provider: LLM provider used by the intent pipeline
        playbook_service: Service that lists available playbooks

    Returns:
        Dict with workflow_steps and step_dependencies, or None if single step.
    """
    if not llm_provider:
        return None

    available_playbooks_metadata = await playbook_service.list_playbooks()
    available_playbooks = available_playbooks_metadata
    playbook_list = []
    for playbook in available_playbooks:
        if hasattr(playbook, "playbook_code"):
            playbook_code = playbook.playbook_code
            name = playbook.name
            description = playbook.description if hasattr(playbook, "description") else None
            tags = playbook.tags if hasattr(playbook, "tags") else []
        elif hasattr(playbook, "metadata"):
            playbook_code = playbook.metadata.playbook_code
            name = playbook.metadata.name
            description = (
                playbook.metadata.description
                if hasattr(playbook.metadata, "description")
                else None
            )
            tags = playbook.metadata.tags if hasattr(playbook.metadata, "tags") else []
        else:
            continue

        playbook_info = f"- {playbook_code}: {name}"
        if description:
            playbook_info += f" ({description[:300]})"
        if tags:
            playbook_info += f" [tags: {', '.join(tags)}]"
        playbook_list.append(playbook_info)

    prompt = f"""Analyze the following user request to determine if it requires multiple playbooks:

User input: "{user_input}"
Initial playbook: {initial_playbook_code}

Available playbooks:
{chr(10).join(playbook_list[:20])}

Determine if this request requires multiple steps. Look for:
- Multiple distinct tasks (e.g., "OCR PDF then generate posts")
- Sequential operations (e.g., "process file then save to book")
- Multiple outputs (e.g., "generate IG posts and YT script")

If single step, return null.
If multi-step, return JSON with workflow_steps array (simplified WorkflowStep with only playbook_code and inputs):

{{
    "is_multi_step": true,
    "workflow_steps": [
        {{
            "playbook_code": "pdf_ocr_processing",
            "inputs": {{
                "pdf_files": ["$context.uploaded_files"]
            }}
        }},
        {{
            "playbook_code": "ig_post_generation",
            "inputs": {{
                "source_content": "$previous.pdf_ocr_processing.outputs.ocr_text",
                "post_count": 5
            }}
        }}
    ],
    "step_dependencies": {{
        "ig_post_generation": ["pdf_ocr_processing"]
    }}
}}

Return only valid JSON or null.
"""

    try:
        if not llm_provider:
            logger.warning("Multi-step detection: llm_provider not available")
            return None

        messages = build_prompt(user_prompt=prompt)
        if not messages:
            logger.warning("Multi-step detection: build_prompt returned empty messages")
            return None
        response_dict = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=None,
        )

        response_text = response_dict.get("text", "")
        if not response_text:
            return None

        result = parse_json_from_response(response_text)
        if result and result.get("is_multi_step"):
            logger.info(
                "Detected multi-step workflow with %s steps",
                len(result.get("workflow_steps", [])),
            )
            return result
        return None

    except Exception as e:
        logger.warning("Multi-step detection failed: %s", e, exc_info=True)
        return None
