"""
Task Extractor Service

Extracts tasks from messages and files using LLM.
"""

import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class TaskExtractor:
    """Extract tasks from content using LLM"""

    def __init__(self, llm_provider=None):
        """
        Initialize TaskExtractor

        Args:
            llm_provider: LLM provider instance (e.g., OpenAI, Anthropic)
        """
        self.llm_provider = llm_provider

    async def extract_tasks_from_content(
        self,
        profile_id: str,
        content: str,
        source_type: str = "message",
        source_id: Optional[str] = None,
        source_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tasks from content using LLM

        Args:
            profile_id: User profile ID
            content: Message text or file content
            source_type: 'message', 'file', or 'conversation'
            source_id: ID of the source (message ID, file ID, etc.)
            source_context: Additional context

        Returns:
            List of extracted tasks with title, description, priority, due_date, etc.
        """
        if not self.llm_provider:
            logger.warning("LLM provider not available, skipping task extraction")
            return []

        try:
            prompt = f"""Extract actionable tasks from the following content:

Content:
{content}

{source_context if source_context else ""}

Please extract all tasks, todos, action items, or planning items mentioned in the content.
IMPORTANT: Only extract tasks that are:
- Actionable (something that can be done)
- Specific (not vague or abstract)
- Time-bound or have a clear outcome

If the content contains:
- Questions or inquiries → DO NOT extract as tasks
- General statements or observations → DO NOT extract as tasks
- Completed actions or past events → DO NOT extract as tasks
- Vague intentions without clear actions → DO NOT extract as tasks

For each task, provide:
- title: A clear, concise task title
- description: Detailed description (if available)
- priority: 'high', 'medium', or 'low' (default: 'medium')
- due_date: Due date in ISO format (YYYY-MM-DD) if mentioned, otherwise null
- estimated_duration: Estimated time in minutes if mentioned, otherwise null
- tags: List of relevant tags or categories

If no actionable tasks are found, return an empty tasks array: {{"tasks": []}}

Return the result as a JSON object with this structure:
{{
  "tasks": [
    {{
      "title": "Task title",
      "description": "Task description",
      "priority": "medium",
      "due_date": "2025-12-01",
      "estimated_duration": 60,
      "tags": ["work", "urgent"]
    }},
    ...
  ]
}}
"""

            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini"
            )

            tasks_data = self._parse_llm_response(response)

            if not tasks_data or "tasks" not in tasks_data:
                logger.warning("No tasks found in LLM response")
                return []

            tasks = tasks_data.get("tasks", [])

            valid_tasks = []
            for task in tasks:
                if isinstance(task, dict) and task.get("title"):
                    title = str(task.get("title", "")).strip()
                    if len(title) > 0:
                        valid_tasks.append(task)
                else:
                    logger.warning(f"Invalid task format: {task}")

            logger.info(f"Extracted {len(valid_tasks)} valid tasks from content (raw: {len(tasks)})")
            if len(valid_tasks) == 0 and len(content) > 100:
                logger.debug(f"No tasks extracted from content (length: {len(content)}). Content preview: {content[:200]}...")

            return valid_tasks

        except Exception as e:
            logger.error(f"Failed to extract tasks from content: {e}", exc_info=True)
            return []

    def _parse_llm_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse LLM response to extract tasks

        Args:
            response: LLM response object

        Returns:
            Parsed tasks data dictionary
        """
        try:
            if hasattr(response, 'choices') and len(response.choices) > 0:
                content = response.choices[0].message.content
            elif isinstance(response, dict):
                content = response.get("content") or response.get("text", "")
            elif isinstance(response, str):
                content = response
            else:
                logger.warning(f"Unexpected response type: {type(response)}")
                return {}

            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            tasks_data = json.loads(content)
            return tasks_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing LLM response: {e}", exc_info=True)
            return {}

