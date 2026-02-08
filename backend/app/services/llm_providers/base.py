"""
LLM Provider Base Class
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class LLMProvider:
    """Base class for LLM providers"""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def chat_completion(
        self, messages: List[Dict[str, str]], model: str = "gpt-4o-mini"
    ) -> str:
        """Abstract method for chat completion"""
        raise NotImplementedError

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        """
        Abstract method for streaming chat completion

        Returns:
            AsyncGenerator that yields chunks from the stream
        """
        raise NotImplementedError
