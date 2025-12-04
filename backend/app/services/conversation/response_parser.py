"""
Response Parser for Agent Mode
Parses two-part agent mode responses into structured data
"""

import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def parse_agent_mode_response(llm_response: str) -> Dict[str, Any]:
    """
    Parse two-part agent mode response

    Expected format:
    Part 1: Understanding & Response (2-4 sentences)
    Part 2: Executable Next Steps (1-3 tasks)

    Args:
        llm_response: Raw LLM response text

    Returns:
        {
            "part1": str,  # Understanding & Response
            "part2": str,  # Executable Next Steps
            "executable_tasks": List[str]  # Extracted task list
        }
    """
    result = {
        "part1": "",
        "part2": "",
        "executable_tasks": []
    }

    if not llm_response or not llm_response.strip():
        logger.warning("Empty LLM response")
        return result

    # Try to find Part 1 and Part 2 markers
    # Look for explicit markers first
    part1_pattern = r"(?:Part\s*1[:\-]?\s*)?(?:Understanding\s*&\s*Response[:\-]?\s*)?(.*?)(?=Part\s*2|Executable\s*Next\s*Steps|$)"
    part2_pattern = r"(?:Part\s*2[:\-]?\s*)?(?:Executable\s*Next\s*Steps[:\-]?\s*)?(.*?)$"

    # Try explicit markers first
    part1_match = re.search(part1_pattern, llm_response, re.IGNORECASE | re.DOTALL)
    part2_match = re.search(part2_pattern, llm_response, re.IGNORECASE | re.DOTALL)

    if part1_match and part2_match:
        result["part1"] = part1_match.group(1).strip()
        result["part2"] = part2_match.group(1).strip()
    else:
        # Fallback: Try to split by common separators
        # Look for patterns like "---", "---", or numbered lists
        separators = [
            r"\n---\n",
            r"\n---\s*\n",
            r"\n\*\*Part\s*1\*\*",
            r"\n\*\*Part\s*2\*\*",
            r"\nI can help you:",
            r"\nExecutable Next Steps:",
        ]

        split_text = None
        for sep in separators:
            parts = re.split(sep, llm_response, flags=re.IGNORECASE)
            if len(parts) >= 2:
                split_text = parts
                break

        if split_text and len(split_text) >= 2:
            result["part1"] = split_text[0].strip()
            result["part2"] = split_text[1].strip()
        else:
            # Last resort: Split by first numbered list or "I can help you"
            # Assume first paragraph is Part 1, rest is Part 2
            lines = llm_response.split('\n')
            part1_lines = []
            part2_start = None

            for i, line in enumerate(lines):
                if re.search(r"I can help you|Executable|Next Steps|1\)|2\)|3\)", line, re.IGNORECASE):
                    part2_start = i
                    break
                part1_lines.append(line)

            if part2_start is not None:
                result["part1"] = '\n'.join(part1_lines).strip()
                result["part2"] = '\n'.join(lines[part2_start:]).strip()
            else:
                # If no clear split, put everything in Part 1
                result["part1"] = llm_response.strip()
                logger.warning("Could not find Part 2 in response, putting everything in Part 1")

    # Extract executable tasks from Part 2
    result["executable_tasks"] = extract_executable_tasks(result["part2"])

    return result


def extract_executable_tasks(part2_text: str) -> List[str]:
    """
    Extract executable tasks from Part 2 text

    Looks for patterns like:
    - "1) [task1], 2) [task2]"
    - "I can help you: task1, task2, task3"
    - Numbered lists
    - Bullet points

    Args:
        part2_text: Part 2 text from agent mode response

    Returns:
        List of extracted task strings
    """
    tasks = []

    if not part2_text or not part2_text.strip():
        return tasks

    # Pattern 1: Numbered list with parentheses "1) task, 2) task"
    numbered_pattern = r'\d+\)\s*([^,，\n]+)'
    matches = re.findall(numbered_pattern, part2_text)
    if matches:
        tasks.extend([m.strip() for m in matches])
        return tasks

    # Pattern 2: "I can help you: task1, task2, task3"
    help_pattern = r"I can help you[:\-]?\s*(.+)"
    help_match = re.search(help_pattern, part2_text, re.IGNORECASE)
    if help_match:
        tasks_text = help_match.group(1)
        # Split by comma or semicolon
        task_items = re.split(r'[,，;；]\s*(?=\d+\)|)', tasks_text)
        tasks.extend([t.strip() for t in task_items if t.strip()])

    # Pattern 3: Bullet points or dashes
    bullet_pattern = r'[•\-\*]\s*([^\n]+)'
    bullet_matches = re.findall(bullet_pattern, part2_text)
    if bullet_matches:
        tasks.extend([m.strip() for m in bullet_matches])

    # Pattern 4: Simple numbered list "1. task"
    simple_numbered = r'\d+\.\s*([^\n]+)'
    simple_matches = re.findall(simple_numbered, part2_text)
    if simple_matches:
        tasks.extend([m.strip() for m in simple_matches])

    # Clean up tasks (remove common prefixes)
    cleaned_tasks = []
    for task in tasks:
        # Remove "I can help you" if it appears
        task = re.sub(r'^I can help you[:\-]?\s*', '', task, flags=re.IGNORECASE)
        # Remove trailing punctuation
        task = task.rstrip('.,;，。；')
        if task and len(task) > 3:  # Filter out very short tasks
            cleaned_tasks.append(task)

    return cleaned_tasks[:5]  # Limit to 5 tasks max

