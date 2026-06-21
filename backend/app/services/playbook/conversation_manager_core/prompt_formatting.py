"""Pure prompt formatting helpers for playbook conversation manager."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

AUTO_EXECUTE_MARKER = "\u26a1"


def build_base_prompt_parts(
    *,
    playbook_name: str,
    sop_content: str,
    user_context: Optional[Mapping[str, Any]],
    target_language: str,
    variant: Optional[Mapping[str, Any]],
    skip_steps: List[int],
    custom_checklist: List[str],
    auto_execute: bool,
) -> List[str]:
    prompt_parts = [
        f"[PLAYBOOK: {playbook_name}]",
        sop_content,
        "[/PLAYBOOK]",
    ]

    if variant:
        if skip_steps:
            prompt_parts.append("\n[SKIP_STEPS]")
            prompt_parts.append(
                f"Skip the following steps: {', '.join(map(str, skip_steps))}"
            )
            prompt_parts.append("[/SKIP_STEPS]")

        if custom_checklist:
            prompt_parts.append("\n[CUSTOM_CHECKLIST]")
            prompt_parts.append("Additional checklist items:")
            prompt_parts.extend(f"- {item}" for item in custom_checklist)
            prompt_parts.append("[/CUSTOM_CHECKLIST]")

    if user_context:
        prompt_parts.append("\n[USER_CONTEXT]")
        prompt_parts.append(f"Identity: {user_context.get('identity', 'N/A')}")
        prompt_parts.append(f"Current Goal: {user_context.get('solving', 'N/A')}")
        prompt_parts.append(f"Challenges: {user_context.get('thinking', 'N/A')}")
        prompt_parts.append("[/USER_CONTEXT]")

    prompt_parts.append("\n[LANGUAGE_INSTRUCTION]")
    prompt_parts.append(f"Always respond in {target_language}.")
    prompt_parts.append(f"Use terminology appropriate for {target_language} locale.")
    prompt_parts.append(
        f"Maintain a conversational, friendly tone in {target_language}."
    )
    prompt_parts.append("[/LANGUAGE_INSTRUCTION]")

    prompt_parts.append("\n[EXECUTION_INSTRUCTIONS]")
    prompt_parts.append("Follow the SOP steps exactly as described.")
    prompt_parts.append(
        "At the end, output structured JSON with the key 'STRUCTURED_OUTPUT'."
    )

    if auto_execute:
        prompt_parts.append(f"\n{AUTO_EXECUTE_MARKER} **AUTO-EXECUTE MODE ENABLED**:")
        prompt_parts.append("- Do NOT ask for user confirmation before executing tools")
        prompt_parts.append("- Execute all tool calls immediately and directly")
        prompt_parts.append("- Skip any 'needs_review' or 'confirmation' steps")
        prompt_parts.append("- Complete all SOP phases in a single response if possible")
        prompt_parts.append("- Generate all required output files without waiting for user input")

    prompt_parts.append("[/EXECUTION_INSTRUCTIONS]")
    return prompt_parts


def build_tool_format_instructions(*, has_slot_info: bool) -> List[str]:
    instructions = [
        "\n## Tool Call Format (Must Follow Strictly)",
        "\nWhen you need to use tools, you **must** use one of the following JSON formats:",
    ]

    if has_slot_info:
        instructions.extend(
            [
                "\n### Format A (Use Tool Slot, Recommended):",
                "```json",
                "{",
                '  "tool_call": {',
                '    "tool_slot": "cms.footer.apply_style",',
                '    "parameters": {',
                '      "footer_content": "..."',
                "    }",
                "  }",
                "}",
                "```",
                "\nUsing tool_slot allows more flexible tool binding, recommend using this format first.",
            ]
        )

    instructions.extend(
        [
            "\n### Format B (Use Concrete Tool ID, Backward Compatible):",
            "```json",
            "{",
            '  "tool_call": {',
            '    "tool_name": "filesystem_list_files",',
            '    "parameters": {',
            '      "path": "./",',
            '      "recursive": true',
            "    }",
            "  }",
            "}",
            "```",
            "\n### Format C (Simplified Format):",
            "```json",
            "{",
            '  "tool_name": "filesystem_write_file",',
            '  "parameters": {',
            '    "file_path": "pages/index.tsx",',
            '    "content": "// file content here"',
            "  }",
            "}",
            "```",
            "\n### Invalid Formats (System Cannot Parse):",
            "- Field names like `tool_code`, `tool_command`, etc.",
            "- Python syntax like `tool_name(arg=value)`",
            "- Function call syntax like `print(filesystem_list_files(...))`",
            "\nAfter tool calls, the system will automatically execute and return results to you.",
        ]
    )
    return instructions


def build_tool_access_sections(
    *,
    slot_info_str: str,
    cached_tools_str: Optional[str],
) -> List[str]:
    sections: List[str] = []
    instructions = build_tool_format_instructions(has_slot_info=bool(slot_info_str))

    if slot_info_str:
        sections.append(slot_info_str)
        sections.append("\n**How to Use Tools:**")
        sections.extend(instructions)

    if cached_tools_str:
        sections.append("\n[AVAILABLE_TOOLS]")
        if slot_info_str:
            sections.append(
                "If no suitable slot is available, you can also directly use the following tools:"
            )
        sections.append(cached_tools_str)
        if not slot_info_str:
            sections.append("\n\n**How to Use Tools:**")
            sections.extend(instructions)
        sections.append("[/AVAILABLE_TOOLS]")
    elif not slot_info_str:
        sections.append("\n[AVAILABLE_TOOLS]")
        sections.extend(instructions)
        sections.append("[/AVAILABLE_TOOLS]")

    return sections


def build_tool_result_message(
    *,
    tool_results: List[Dict[str, Any]],
    tool_schemas: Mapping[str, Optional[Dict[str, Any]]],
    auto_execute: bool,
) -> str:
    results_text = "**Tool Call Results:**\n\n"
    for index, result in enumerate(tool_results, 1):
        tool_name = result.get("tool_name", "unknown")
        success = result.get("success", False)

        if success:
            result_value = result.get("result", "Execution successful")
            results_text += f"{index}. **{tool_name}**: Execution successful\n"
            if isinstance(result_value, (dict, list)):
                result_str = json.dumps(result_value, ensure_ascii=False, indent=2)
                results_text += f"   Result:\n```json\n{result_str}\n```\n\n"
            else:
                result_str = str(result_value)[:500]
                results_text += f"   Result: {result_str}\n\n"
            continue

        error_msg = result.get("error", "Execution failed")
        results_text += f"{index}. **{tool_name}**: Execution failed\n"
        results_text += f"   Error: {error_msg}\n\n"

        tool_schema = tool_schemas.get(tool_name)
        if tool_schema:
            results_text += "   **Tool Definition:**\n"
            results_text += f"   - Tool Name: `{tool_schema.get('name', tool_name)}`\n"
            results_text += f"   - Description: {tool_schema.get('description', 'N/A')}\n"
            input_schema = tool_schema.get("input_schema") or {}
            params = input_schema.get("properties", {})
            if params:
                results_text += "   - **Correct Parameters:**\n"
                required_params = input_schema.get("required", [])
                for param_name, param_def in params.items():
                    param_type = param_def.get("type", "unknown")
                    param_desc = param_def.get("description", "")
                    req_marker = " (required)" if param_name in required_params else ""
                    results_text += (
                        f"     - `{param_name}` ({param_type}){req_marker}: "
                        f"{param_desc}\n"
                    )
            results_text += "\n"

    if auto_execute:
        results_text += (
            f"\n**{AUTO_EXECUTE_MARKER} AUTO-EXECUTE MODE: You MUST continue executing "
            "the next steps in the SOP immediately.**\n"
        )
        results_text += "- Review the tool results above\n"
        results_text += "- Immediately call the next required tool from the SOP\n"
        results_text += "- Do NOT stop or ask for confirmation\n"
        results_text += "- Continue until all SOP phases are complete\n"
    else:
        results_text += (
            "Please continue processing based on the above tool call results. If tool calls "
            "failed, please retry with the correct parameters from the tool definition.\n"
        )

    return results_text
