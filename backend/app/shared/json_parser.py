"""
JSON Parser Utilities
Extract structured JSON data from LLM responses

This module provides a unified JSON parsing utility that can handle:
- Direct JSON strings
- JSON in markdown code blocks (```json ... ```)
- JSON embedded in text with other content
- Nested JSON structures

Used by:
- ExecutionPlanGenerator: Parse execution plans from LLM responses
- PlaybookRunner: Parse tool calls from LLM responses
"""
import json
import logging
from typing import Optional, Dict, Any, List, Union

logger = logging.getLogger(__name__)


def parse_json_from_llm_response(response: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from LLM response.

    Handles multiple formats:
    - Direct JSON strings
    - JSON in markdown code blocks (```json ... ```)
    - JSON embedded in text

    This function is robust and can handle:
    - Multiple JSON objects in the same response (returns the first/largest)
    - Nested JSON structures
    - JSON with extra whitespace or formatting

    Args:
        response: LLM response string that may contain JSON

    Returns:
        Parsed JSON object (dict), or None if parsing fails

    Example:
        >>> parse_json_from_llm_response('{"key": "value"}')
        {'key': 'value'}

        >>> parse_json_from_llm_response('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}

        >>> parse_json_from_llm_response('Some text before {"key": "value"} and after')
        {'key': 'value'}
    """
    if not response or not isinstance(response, str):
        return None

    try:
        # Try direct parse first (fastest path)
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from response (handle markdown code blocks and embedded JSON)
    try:
        cleaned = response.strip()

        # Handle markdown code blocks
        if cleaned.startswith('```'):
            # Find the first newline after ```
            first_newline = cleaned.find('\n')
            if first_newline > 0:
                cleaned = cleaned[first_newline:].strip()
            # Remove trailing ```
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3].strip()

        # Find JSON object in response
        # Use rfind to get the largest/most complete JSON object
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1

        if start >= 0 and end > start:
            json_str = cleaned[start:end]

            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as e:
                # Log parsing error for debugging
                logger.debug(f"JSON parse error at position {e.pos}: {e.msg}")
                if e.pos:
                    snippet_start = max(0, e.pos - 50)
                    snippet_end = min(len(json_str), e.pos + 50)
                    logger.debug(f"JSON snippet around error: {json_str[snippet_start:snippet_end]}")

                # Try to find a smaller valid JSON object
                # This handles cases where there's extra content after the JSON
                for potential_end in range(end - 1, start, -1):
                    try:
                        smaller_json = cleaned[start:potential_end + 1]
                        parsed = json.loads(smaller_json)
                        if isinstance(parsed, dict):
                            logger.debug(f"Successfully parsed smaller JSON object (length: {len(smaller_json)})")
                            return parsed
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        logger.warning(f"Error during JSON extraction from LLM response: {e}")

    # Failed to parse
    logger.debug(f"Failed to parse JSON from response (first 500 chars): {response[:500]}")
    logger.debug(f"Response length: {len(response)} chars")
    return None


def parse_json_array_from_llm_response(response: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parse JSON array from LLM response.

    Similar to parse_json_from_llm_response but expects an array of objects.

    Args:
        response: LLM response string that may contain a JSON array

    Returns:
        Parsed JSON array (list of dicts), or None if parsing fails
    """
    if not response or not isinstance(response, str):
        return None

    try:
        # Try direct parse first
        parsed = json.loads(response)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from response
    try:
        cleaned = response.strip()

        # Handle markdown code blocks
        if cleaned.startswith('```'):
            first_newline = cleaned.find('\n')
            if first_newline > 0:
                cleaned = cleaned[first_newline:].strip()
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3].strip()

        # Find JSON array in response
        start = cleaned.find('[')
        end = cleaned.rfind(']') + 1

        if start >= 0 and end > start:
            json_str = cleaned[start:end]

            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError as e:
                logger.debug(f"JSON array parse error at position {e.pos}: {e.msg}")

    except Exception as e:
        logger.warning(f"Error during JSON array extraction: {e}")

    return None

