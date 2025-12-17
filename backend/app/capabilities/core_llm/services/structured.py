"""
Core LLM: Structured Extract Service
Extract structured JSON from long text based on schema/description
"""

import logging
from typing import Dict, Any, Optional

from ....shared.llm_utils import build_prompt, call_llm, extract_json_from_text

logger = logging.getLogger(__name__)


async def extract(
    text: str,
    schema_description: str,
    example_output: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[Any] = None,
    locale: Optional[str] = None,
    target_language: Optional[str] = None,
    profile_id: Optional[str] = None  # Accept but not used (for compatibility with workflow_orchestrator)
) -> Dict[str, Any]:
    """
    Extract structured JSON from long text based on schema/description

    Args:
        text: Long text to extract from
        schema_description: Expected JSON schema description
        example_output: Example output (optional)
        llm_provider: LLM provider object (optional)
        locale: Locale code (e.g., "zh-TW", "en"). Deprecated: use target_language instead.
        target_language: Target language for extraction (e.g., "zh-TW", "en", "ja-JP").
                        Primary parameter. Priority: target_language > locale

    Returns:
        Dict containing:
            - extracted_data: Extracted JSON data
            - confidence: Confidence score (0-1)
    """
    try:
        if not llm_provider:
            # Use the standard system method for creating LLM provider (same as workspace chat)
            from ....shared.llm_provider_helper import create_llm_provider_manager, get_llm_provider_from_settings
            llm_manager = create_llm_provider_manager()
            llm_provider = get_llm_provider_from_settings(llm_manager)

        target_lang = target_language or locale

        system_prompt = f"""You are a professional data extraction assistant. Please extract structured data from the provided text.

Requirements:
1. Extract data according to the following schema description: {schema_description}
2. Only extract information explicitly mentioned in the text, do not infer or supplement
3. If a field has no corresponding information, set it to null or omit the field
4. Output format must be a valid JSON object
5. **CRITICAL**: If the schema requires an array (e.g., "tasks": [...]), ALWAYS return an array, even if there's only one item. Never return a single object when an array is expected."""

        if target_lang:
            from .generate import _get_language_instruction
            lang_instruction = _get_language_instruction(target_lang)
            system_prompt += f"\n\nLanguage Requirements:\n{lang_instruction}"

        if example_output:
            import json
            system_prompt += f"\n\nExample output format:\n```json\n{json.dumps(example_output, ensure_ascii=False, indent=2)}\n```"

        # Build user prompt
        user_prompt = f"""Please extract structured data from the following text:

---
{text}
---

Please output the extraction result in JSON format."""

        # Build messages
        messages = build_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Get conversation model from system settings (same as generate.py)
        from ....services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")

        model_to_use = None
        if chat_setting and chat_setting.value:
            model_to_use = str(chat_setting.value)

        # Call LLM
        result = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_to_use,
            temperature=0.3  # Use lower temperature for structured extraction
        )

        # Extract JSON from response
        response_text = result.get('text', '')
        logger.debug(f"Structured extract LLM response (first 500 chars): {response_text[:500]}")
        extracted_data = extract_json_from_text(response_text)

        if not extracted_data:
            logger.warning(f"Failed to extract JSON from LLM response. Response text: {response_text[:200]}")
            extracted_data = {}
            confidence = 0.0
        else:
            # Simple confidence calculation (can be adjusted based on actual needs)
            confidence = 0.8 if len(extracted_data) > 0 else 0.0
            logger.debug(f"Extracted data keys: {list(extracted_data.keys())}")
            for key, value in extracted_data.items():
                if value is None:
                    logger.warning(f"Extracted data key '{key}' is None")
                elif isinstance(value, list) and len(value) == 0:
                    logger.warning(f"Extracted data key '{key}' is empty list")
                elif isinstance(value, dict) and len(value) == 0:
                    logger.warning(f"Extracted data key '{key}' is empty dict")

        logger.info(f"Extracted structured data ({len(extracted_data)} keys, confidence: {confidence:.2f})")

        return {
            "extracted_data": extracted_data,
            "confidence": confidence
        }

    except Exception as e:
        logger.error(f"Structured extraction failed: {e}")
        raise
