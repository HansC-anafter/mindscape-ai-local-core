"""
Content Generator Service

Generates summaries and drafts from content using LLM.
"""

import logging
import json
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Generate summaries and drafts from content using LLM"""

    def __init__(self, llm_provider=None):
        """
        Initialize ContentGenerator

        Args:
            llm_provider: LLM provider instance (e.g., OpenAI, Anthropic)
        """
        self.llm_provider = llm_provider

    async def generate_summary(
        self,
        profile_id: str,
        content: str,
        source_type: str = "message",
        source_id: Optional[str] = None,
        source_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate summary from content using LLM

        Args:
            profile_id: User profile ID
            content: Message text or file content
            source_type: 'message', 'file', or 'conversation'
            source_id: ID of the source (message ID, file ID, etc.)
            source_context: Additional context

        Returns:
            Dictionary containing summary text and metadata
        """
        if not self.llm_provider:
            logger.warning("LLM provider not available, cannot generate summary")
            return {"summary": "", "error": "LLM provider not available"}

        try:
            prompt = f"""Generate a concise summary of the following content:

Content:
{content}

{source_context if source_context else ""}

Please provide:
1. A brief summary (2-3 sentences)
2. Key points (3-5 bullet points)
3. Main themes or topics

Return the result as a JSON object:
{{
  "summary": "Brief summary text",
  "key_points": ["point 1", "point 2", ...],
  "themes": ["theme 1", "theme 2", ...]
}}
"""

            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini"
            )

            summary_data = self._parse_llm_response(response)

            if not summary_data:
                return {"summary": "", "error": "Failed to parse LLM response"}

            return {
                "summary": summary_data.get("summary", ""),
                "key_points": summary_data.get("key_points", []),
                "themes": summary_data.get("themes", []),
                "source_type": source_type,
                "source_id": source_id
            }

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}", exc_info=True)
            return {"summary": "", "error": str(e)}

    async def generate_draft(
        self,
        profile_id: str,
        content: str,
        format: str = "blog_post",
        source_type: str = "message",
        source_id: Optional[str] = None,
        source_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate draft content using LLM

        Args:
            profile_id: User profile ID
            content: Source content or requirements
            format: Output format ('blog_post', 'article', 'report', 'summary')
            source_type: 'message', 'file', or 'conversation'
            source_id: ID of the source
            source_context: Additional context

        Returns:
            Dictionary containing draft content and metadata
        """
        if not self.llm_provider:
            logger.warning("LLM provider not available, cannot generate draft")
            return {"draft": "", "error": "LLM provider not available"}

        try:
            format_instructions = {
                "blog_post": "Write a blog post with title, introduction, main content, and conclusion",
                "article": "Write an article with clear structure and sections",
                "report": "Write a report with executive summary, findings, and recommendations",
                "summary": "Write a detailed summary with key sections"
            }

            prompt = f"""Generate {format_instructions.get(format, 'content')} based on the following:

Content/Requirements:
{content}

{source_context if source_context else ""}

Please provide:
1. Title
2. Full content in the requested format
3. Suggested tags or categories

Return the result as a JSON object:
{{
  "title": "Content title",
  "content": "Full draft content",
  "tags": ["tag1", "tag2", ...],
  "format": "{format}"
}}
"""

            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini"
            )

            draft_data = self._parse_llm_response(response)

            if not draft_data:
                return {"draft": "", "error": "Failed to parse LLM response"}

            return {
                "title": draft_data.get("title", ""),
                "content": draft_data.get("content", ""),
                "tags": draft_data.get("tags", []),
                "format": format,
                "source_type": source_type,
                "source_id": source_id
            }

        except Exception as e:
            logger.error(f"Failed to generate draft: {e}", exc_info=True)
            return {"draft": "", "error": str(e)}

    def _parse_llm_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse LLM response to extract structured data

        Args:
            response: LLM response object

        Returns:
            Parsed data dictionary
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

            data = json.loads(content)
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing LLM response: {e}", exc_info=True)
            return {}

