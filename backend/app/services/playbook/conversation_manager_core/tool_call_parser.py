import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOOL_NAME_ALIASES = {
    "filesystem.list_files": "filesystem_list_files",
    "filesystem.read_file": "filesystem_read_file",
    "filesystem.write_file": "filesystem_write_file",
    "filesystem.search": "filesystem_search",
    "fs.list_files": "filesystem_list_files",
    "fs.read_file": "filesystem_read_file",
    "fs.write_file": "filesystem_write_file",
    "fs.search": "filesystem_search",
    "list_files": "filesystem_list_files",
    "read_file": "filesystem_read_file",
    "write_file": "filesystem_write_file",
}

STRUCTURED_OUTPUT_KEYS = {
    "project_data",
    "work_rhythm_data",
    "onboarding_task",
    "STRUCTURED_OUTPUT",
}


def normalize_tool_name(tool_name: str) -> str:
    return TOOL_NAME_ALIASES.get(tool_name, tool_name)


def parse_python_style_tool_call(text: str) -> List[Dict[str, Any]]:
    """
    Parse Python-style function calls like:
    - filesystem_read_file('path')
    - print(filesystem_list_files(path='.'))
    - fs.read_file('path') -> maps to filesystem_read_file
    """
    tool_calls = []

    for alias, canonical_name in TOOL_NAME_ALIASES.items():
        escaped_alias = alias.replace(".", r"\.")
        pattern = rf"{escaped_alias}\s*\(([^)]*)\)"
        matches = re.findall(pattern, text)

        for args_str in matches:
            parameters: Dict[str, Any] = {}
            simple_match = re.match(r"^\s*['\"]([^'\"]+)['\"]\s*$", args_str)
            if simple_match:
                parameters["path"] = simple_match.group(1)
            else:
                kv_matches = re.findall(r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]", args_str)
                for key, value in kv_matches:
                    parameters[key] = value

                bool_matches = re.findall(r"(\w+)\s*=\s*(True|False)", args_str)
                for key, value in bool_matches:
                    parameters[key] = value == "True"

            if parameters:
                tool_calls.append(
                    {"tool_name": canonical_name, "parameters": parameters}
                )
                logger.info(
                    "Parsed Python-style tool call: %s -> %s(%s)",
                    alias,
                    canonical_name,
                    parameters,
                )

    return tool_calls


def _normalize_tool_entry(result: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = result.get("tool_name")
    if tool_name:
        normalized_name = normalize_tool_name(tool_name)
        if normalized_name != tool_name:
            result["tool_name"] = normalized_name
            logger.info("Normalized tool name: %s -> %s", tool_name, normalized_name)
    return result


def _to_tool_call_payload(tool_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "tool_slot" in tool_data:
        return {
            "tool_slot": tool_data["tool_slot"],
            "parameters": tool_data.get("parameters", tool_data.get("args", {})),
        }
    if "tool_name" in tool_data:
        normalized = _normalize_tool_entry(dict(tool_data))
        return {
            "tool_name": normalized["tool_name"],
            "parameters": normalized.get("parameters", normalized.get("args", {})),
        }
    return None


def _looks_like_structured_output(data: Dict[str, Any]) -> bool:
    return any(key in data for key in STRUCTURED_OUTPUT_KEYS)


def normalize_tool_call_json(parsed_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize various incorrect tool call formats to standard format.

    Handles:
    - tool_call: standard format
    - tool_code: LLM sometimes uses this instead
    - tool_command: another variant
    - tool_calls: array format (returns first item)
    """
    if "tool_call" in parsed_json and isinstance(parsed_json["tool_call"], dict):
        return _normalize_tool_entry(dict(parsed_json["tool_call"]))

    for alt_key in ["tool_code", "tool_command", "function_call", "call"]:
        if alt_key not in parsed_json:
            continue

        data = parsed_json[alt_key]
        if isinstance(data, dict):
            if "tool_slot" in data:
                logger.info(
                    "Normalized '%s' to 'tool_call' (tool_slot format)",
                    alt_key,
                )
                return {
                    "tool_slot": data["tool_slot"],
                    "parameters": data.get("parameters", {}),
                }
            if "tool_name" in data:
                logger.info(
                    "Normalized '%s' to 'tool_call' (tool_name format)",
                    alt_key,
                )
                return _normalize_tool_entry(
                    {
                        "tool_name": data["tool_name"],
                        "parameters": data.get("parameters", {}),
                    }
                )
        elif isinstance(data, str) and any(
            tool in data
            for tool in ["filesystem_", "read_file", "write_file", "list_files"]
        ):
            logger.info(
                "Found Python-style tool call in '%s' string, attempting to parse",
                alt_key,
            )
            parsed_calls = parse_python_style_tool_call(data)
            if parsed_calls:
                logger.info(
                    "Successfully parsed Python-style tool call from '%s': %s",
                    alt_key,
                    parsed_calls[0].get("tool_name"),
                )
                return parsed_calls[0]

    calls = parsed_json.get("tool_calls")
    if isinstance(calls, list) and calls:
        first = calls[0]
        if isinstance(first, dict):
            if "tool_slot" in first:
                logger.info(
                    "Normalized 'tool_calls' array to single tool_call (tool_slot format)"
                )
                return {
                    "tool_slot": first["tool_slot"],
                    "parameters": first.get("parameters", {}),
                }
            if "tool_name" in first:
                logger.info(
                    "Normalized 'tool_calls' array to single tool_call (tool_name format)"
                )
                return _normalize_tool_entry(
                    {
                        "tool_name": first["tool_name"],
                        "parameters": first.get("parameters", {}),
                    }
                )
            if "tool_call" in first and isinstance(first["tool_call"], dict):
                nested = _to_tool_call_payload(first["tool_call"])
                if nested:
                    return nested

    return None


def parse_tool_calls_from_response(assistant_message: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from LLM response across JSON, markdown, and python-style fallbacks.
    """
    from backend.app.shared.json_parser import (
        parse_json_array_from_llm_response,
        parse_json_from_llm_response,
    )

    tool_calls: List[Dict[str, Any]] = []

    try:
        parsed_json = parse_json_from_llm_response(assistant_message)
        if parsed_json:
            normalized = normalize_tool_call_json(parsed_json)
            if normalized and isinstance(normalized, dict):
                payload = _to_tool_call_payload(normalized)
                if payload:
                    logger.info("Parsed 1 tool call (normalized)")
                    return [payload]

            if "tool_call" in parsed_json and isinstance(parsed_json["tool_call"], dict):
                payload = _to_tool_call_payload(parsed_json["tool_call"])
                if payload:
                    logger.info("Parsed 1 tool call from JSON")
                    return [payload]

            if "tool_slot" in parsed_json and isinstance(parsed_json.get("tool_slot"), str):
                if not _looks_like_structured_output(parsed_json):
                    return [
                        {
                            "tool_slot": parsed_json["tool_slot"],
                            "parameters": parsed_json.get(
                                "parameters",
                                parsed_json.get("args", {}),
                            ),
                        }
                    ]
            if "tool_name" in parsed_json and isinstance(parsed_json.get("tool_name"), str):
                if not _looks_like_structured_output(parsed_json):
                    return [
                        {
                            "tool_name": normalize_tool_name(parsed_json["tool_name"]),
                            "parameters": parsed_json.get(
                                "parameters",
                                parsed_json.get("args", {}),
                            ),
                        }
                    ]

        parsed_array = parse_json_array_from_llm_response(assistant_message)
        if parsed_array and isinstance(parsed_array, list):
            for item in parsed_array:
                if not isinstance(item, dict):
                    continue
                if "tool_call" in item and isinstance(item["tool_call"], dict):
                    payload = _to_tool_call_payload(item["tool_call"])
                    if payload:
                        tool_calls.append(payload)
                elif "tool_slot" in item and isinstance(item.get("tool_slot"), str):
                    tool_calls.append(
                        {
                            "tool_slot": item["tool_slot"],
                            "parameters": item.get("parameters", item.get("args", {})),
                        }
                    )
                elif "tool_name" in item and isinstance(item.get("tool_name"), str):
                    tool_calls.append(
                        {
                            "tool_name": normalize_tool_name(item["tool_name"]),
                            "parameters": item.get("parameters", item.get("args", {})),
                        }
                    )

            if tool_calls:
                logger.info("Parsed %d tool call(s) from JSON array", len(tool_calls))
                return tool_calls

        matches = re.findall(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            assistant_message,
            re.DOTALL,
        )
        for match in matches:
            parsed = parse_json_from_llm_response(match)
            if not parsed:
                continue

            normalized = normalize_tool_call_json(parsed)
            if normalized and isinstance(normalized, dict):
                payload = _to_tool_call_payload(normalized)
                if payload:
                    tool_calls.append(payload)
                    continue

            if "tool_call" in parsed and isinstance(parsed["tool_call"], dict):
                payload = _to_tool_call_payload(parsed["tool_call"])
                if payload:
                    tool_calls.append(payload)
            elif "tool_slot" in parsed and isinstance(parsed.get("tool_slot"), str):
                if not _looks_like_structured_output(parsed):
                    tool_calls.append(
                        {
                            "tool_slot": parsed["tool_slot"],
                            "parameters": parsed.get(
                                "parameters",
                                parsed.get("args", {}),
                            ),
                        }
                    )
            elif "tool_name" in parsed and isinstance(parsed.get("tool_name"), str):
                if not _looks_like_structured_output(parsed):
                    tool_calls.append(
                        {
                            "tool_name": normalize_tool_name(parsed["tool_name"]),
                            "parameters": parsed.get(
                                "parameters",
                                parsed.get("args", {}),
                            ),
                        }
                    )

        if tool_calls:
            logger.info(
                "Parsed %d tool call(s) from markdown code blocks",
                len(tool_calls),
            )
            return tool_calls

        python_calls = parse_python_style_tool_call(assistant_message)
        if python_calls:
            logger.info(
                "Parsed %d tool call(s) from Python-style syntax (fallback)",
                len(python_calls),
            )
            return python_calls
    except Exception as exc:
        logger.warning(
            "Failed to parse tool calls from response: %s",
            exc,
            exc_info=True,
        )

    return tool_calls
