"""
Ollama LLM Provider (via OpenAI-compatible API)
"""

from typing import Dict, List, Optional
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local Ollama provider (via OpenAI-compatible API)"""

    def __init__(
        self, base_url: str = "http://localhost:11434", api_key: str = "ollama"
    ):
        super().__init__(api_key=api_key)
        self.base_url = base_url
        # Ensure base_url ends with /v1 for OpenAI compatibility if not present
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url.rstrip('/')}/v1"

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str:
        try:
            import openai

            client = openai.AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens is not None:
                request_params["max_tokens"] = max_tokens

            # Handle streaming vs non-streaming
            if stream:
                request_params["stream"] = True
                stream = await client.chat.completions.create(**request_params)

                full_text = ""
                async for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            full_text += delta.content

                logger.info(
                    f"Ollama streaming response received: {len(full_text)} chars"
                )
                return full_text
            else:
                response = await client.chat.completions.create(**request_params)

                response_text = None
                if response.choices and len(response.choices) > 0:
                    message = response.choices[0].message
                    if hasattr(message, "content"):
                        response_text = message.content

                return response_text or ""

        except ImportError:
            raise Exception("OpenAI package not installed (required for Ollama client)")
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "llama3",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        """
        Streaming chat completion - returns stream object for SSE
        """
        try:
            import openai

            client = openai.AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }

            if max_tokens is not None:
                request_params["max_tokens"] = max_tokens

            stream = await client.chat.completions.create(**request_params)
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        yield delta.content
        except ImportError:
            raise Exception("OpenAI package not installed (required for Ollama client)")
        except Exception as e:
            logger.error(f"Ollama streaming API error: {e}", exc_info=True)
            raise
