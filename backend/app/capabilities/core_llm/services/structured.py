"""
Core LLM: Structured Extract Service
Extract structured JSON from long text based on schema/description.
"""

import json
import logging
import re
from typing import Dict, Any, Optional

try:
    from shared.llm_utils import build_prompt, call_llm, extract_json_from_text
except ImportError:  # pragma: no cover - backend package import path fallback
    from ....shared.llm_utils import build_prompt, call_llm, extract_json_from_text

logger = logging.getLogger(__name__)


def _infer_outer_array_key(schema_description: str) -> Optional[str]:
    """Infer the wrapper key expected when a model returns a bare array."""
    if not schema_description:
        return None

    patterns = [
        r"with an? ['\"]([A-Za-z_][\w-]*)['\"] property",
        r"['\"]([A-Za-z_][\w-]*)['\"]\s+property",
        r"['\"]([A-Za-z_][\w-]*)['\"]\s*:\s*array",
        r"([A-Za-z_][\w-]*)\s*:\s*array",
    ]
    for pattern in patterns:
        match = re.search(pattern, schema_description, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _normalize_extracted_data(
    extracted_data: Any,
    schema_description: str,
) -> Dict[str, Any]:
    """Normalize model JSON into the tool's object-shaped output contract."""
    if isinstance(extracted_data, dict):
        return extracted_data

    if isinstance(extracted_data, list):
        outer_key = _infer_outer_array_key(schema_description)
        if outer_key:
            logger.warning(
                "Structured extraction returned a bare list; wrapping it with schema key '%s'",
                outer_key,
            )
            return {outer_key: extracted_data}
        logger.warning(
            "Structured extraction returned a bare list without an inferred schema key; using 'items'"
        )
        return {"items": extracted_data}

    if extracted_data is None:
        return {}

    logger.warning(
        "Structured extraction returned unsupported JSON type %s; storing it under 'value'",
        type(extracted_data).__name__,
    )
    return {"value": extracted_data}


async def extract(
    text: str,
    schema_description: str,
    example_output: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[Any] = None,
    locale: Optional[str] = None,
    target_language: Optional[str] = None,
    profile_id: Optional[str] = None,  # Accept but not used (for compatibility with workflow_orchestrator)
    workspace_id: Optional[str] = None,
    route_context: Optional[Dict[str, Any]] = None,
    stage_name: Optional[str] = "structured_extract",
    purpose: str = "core_llm.structured_extract",
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

        try:
            from shared.llm_provider_helper import get_model_name_from_chat_model
        except ImportError:  # pragma: no cover - backend package import path fallback
            from ....shared.llm_provider_helper import get_model_name_from_chat_model

        model_to_use = get_model_name_from_chat_model()

        # Call LLM
        result = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_to_use,
            temperature=0.3,
            max_tokens=8192,
            workspace_id=workspace_id,
            profile_id=profile_id,
            route_context=route_context,
            stage_name=stage_name,
            purpose=purpose,
        )

        # Extract JSON from response
        response_text = result.get('text', '')
        logger.debug(f"Structured extract LLM response (first 500 chars): {response_text[:500]}")
        raw_extracted_data = extract_json_from_text(response_text)
        extracted_data = _normalize_extracted_data(raw_extracted_data, schema_description)

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


async def extract_structured(
    text: str,
    schema: Any,
    example_output: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[Any] = None,
    locale: Optional[str] = None,
    target_language: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible wrapper returning only the extracted payload.

    Older callers import ``extract_structured(prompt, schema)`` and expect the
    parsed JSON object directly. Keep that contract while the canonical service
    exposes ``extract(...)`` returning ``{extracted_data, confidence}``.
    """
    if isinstance(schema, str):
        schema_description = schema
    else:
        schema_description = json.dumps(schema, ensure_ascii=False, indent=2)

    result = await extract(
        text=text,
        schema_description=schema_description,
        example_output=example_output,
        llm_provider=llm_provider,
        locale=locale,
        target_language=target_language,
        profile_id=profile_id,
    )
    extracted_data = result.get("extracted_data")
    return extracted_data if isinstance(extracted_data, dict) else {}
