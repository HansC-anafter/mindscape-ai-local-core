"""
LLM-based Intent Extractor

Lightweight helper to extract intents/themes from user message + context
using existing core_llm generate service.
"""

import logging
import os
import json
import re
from typing import Dict, Any, List, Optional

try:
    from ..capabilities.core_llm.services.generate import run as llm_generate
except Exception:
    llm_generate = None

logger = logging.getLogger(__name__)


class IntentLLMExtractor:
    """Extract intents/themes from message + context using LLM"""

    def __init__(self, default_locale: str = "en"):
        self.default_locale = default_locale

    async def extract(
        self,
        message: str,
        context: str = "",
        locale: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract intents/themes using LLM.

        Args:
            message: User message
            context: Optional context string (files, timeline, history)
            locale: Target language

        Returns:
            Dict with:
            - intents: List[Dict[str, str]] with keys "title" and "summary"
            - themes: List[str] of theme strings
        """
        if not llm_generate:
            logger.warning("core_llm generate not available, skipping LLM intent extraction")
            return {"intents": [], "themes": []}

        system_prompt = """You are an intent extraction assistant. Analyze the user's message and context to extract:
1. Intents: What the user wants to accomplish (each with a title and summary)
2. Themes: Key topics or concepts mentioned

Return a JSON object with this exact structure:
{
  "intents": [
    {"title": "short intent title", "summary": "brief description"},
    {"title": "another intent", "summary": "description"}
  ],
  "themes": ["theme1", "theme2", "theme3"]
}

Guidelines:
- Keep intent titles under 30 characters
- Keep intent summaries under 100 characters
- Keep theme strings under 50 characters
- Return empty arrays if nothing is found
- Do not add explanations, only JSON"""

        user_prompt = f"""User Message:
{message}

Workspace Context:
{context or 'No additional context available'}

Extract intents and themes from the message and context above."""

        try:
            logger.info(f"IntentLLMExtractor: Calling LLM with message length {len(message)}, context length {len(context)}")
            result = await llm_generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.2,
                llm_provider=None,
                target_language=locale or self.default_locale
            )
            text = (result or {}).get("text", "") or ""
            logger.info(f"IntentLLMExtractor: LLM returned text length {len(text)}, preview: {text[:200]}...")

            # Parse JSON from response
            extracted = self._parse_json_response(text)
            logger.info(f"IntentLLMExtractor: Parsed JSON: {extracted}")

            # Normalize response format
            intents = extracted.get("intents", [])
            themes = extracted.get("themes", [])

            # Ensure intents have correct structure
            normalized_intents = []
            for intent in intents if isinstance(intents, list) else []:
                if isinstance(intent, dict):
                    normalized_intents.append({
                        "title": intent.get("title", ""),
                        "summary": intent.get("summary", "")
                    })
                elif isinstance(intent, str):
                    # Fallback: if intent is a string, use it as title
                    normalized_intents.append({
                        "title": intent,
                        "summary": ""
                    })

            # Ensure themes are strings
            normalized_themes = []
            for theme in themes if isinstance(themes, list) else []:
                if isinstance(theme, str):
                    normalized_themes.append(theme)
                elif isinstance(theme, dict):
                    # If theme is a dict, try to extract a string value
                    normalized_themes.append(str(theme.get("name", theme.get("title", str(theme)))))

            return {
                "intents": normalized_intents,
                "themes": normalized_themes
            }
        except Exception as e:
            logger.warning(f"LLM intent extraction failed: {e}", exc_info=True)
            return {"intents": [], "themes": []}

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response text"""
        if not text:
            return {}

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try to find JSON array (if response is just an array)
        try:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                array_data = json.loads(match.group(0))
                # If it's an array, try to wrap it
                if isinstance(array_data, list):
                    return {"intents": array_data, "themes": []}
        except (json.JSONDecodeError, AttributeError):
            pass

        logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}...")
        return {}

