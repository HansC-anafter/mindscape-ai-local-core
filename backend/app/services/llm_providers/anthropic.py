"""
Anthropic Claude LLM Provider
"""

from typing import Dict, List
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider"""

    async def chat_completion(
        self, messages: List[Dict[str, str]], model: str = "claude-3-sonnet-20240229"
    ) -> str:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)

            system_message = ""
            conversation_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    conversation_messages.append(msg)

            response = await client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0.7,
                system=system_message,
                messages=conversation_messages,
            )

            return response.content[0].text

        except ImportError:
            raise Exception("Anthropic package not installed")
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise
