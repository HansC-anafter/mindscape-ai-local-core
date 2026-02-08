"""
JSON Parsing Utilities for Intent Analysis
"""

import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def parse_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from LLM response, handling markdown code blocks

    Args:
        response_text: Raw response text from LLM

    Returns:
        Parsed JSON dict, or None if parsing fails
    """
    if not response_text or not response_text.strip():
        return None

    # First, try direct JSON parsing
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    # Pattern 1: ```json ... ```
    json_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(json_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Pattern 2: ``` ... ``` (without json label)
    code_block_pattern = r"```\s*(\{.*?\})\s*```"
    match = re.search(code_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Pattern 3: Remove markdown markers and try again
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Pattern 4: Find the largest JSON object in the text
    # Match balanced braces
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(response_text):
        if char == "{":
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start_idx >= 0:
                json_str = response_text[start_idx : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

    logger.warning(
        f"Failed to parse JSON from response. Response preview: {response_text[:500]}"
    )
    return None


# Alias for backward compatibility
_parse_json_from_response = parse_json_from_response
