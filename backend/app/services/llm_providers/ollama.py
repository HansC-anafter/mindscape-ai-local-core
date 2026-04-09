"""
Ollama LLM Provider (via OpenAI-compatible API)
"""

import json
import logging
from typing import Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

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

    def _native_base_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return self.base_url[: -len("/v1")]
        return self.base_url.rstrip("/")

    def is_model_available(self, model: str) -> tuple[bool, Optional[str]]:
        normalized_model = (model or "").strip()
        if not normalized_model:
            return False, "Ollama model name is empty."

        tags_url = f"{self._native_base_url()}/api/tags"
        try:
            request = urllib_request.Request(
                tags_url,
                headers={"Accept": "application/json"},
            )
            with urllib_request.urlopen(request, timeout=2.0) as response:
                payload = json.load(response)
        except urllib_error.URLError as exc:
            logger.warning("Failed to query Ollama tags from %s: %s", tags_url, exc)
            return (
                False,
                f"Ollama model availability check failed for '{normalized_model}': {exc}",
            )
        except Exception as exc:
            logger.warning("Unexpected Ollama tags error from %s: %s", tags_url, exc)
            return (
                False,
                f"Ollama model availability check failed for '{normalized_model}': {exc}",
            )

        models = payload.get("models") if isinstance(payload, dict) else []
        installed_names: set[str] = set()
        for item in models:
            if not isinstance(item, dict):
                continue
            for key in ("name", "model"):
                raw_value = item.get(key)
                if isinstance(raw_value, str) and raw_value.strip():
                    installed_names.add(raw_value.strip())

        if normalized_model in installed_names:
            return True, None
        if ":" not in normalized_model and f"{normalized_model}:latest" in installed_names:
            return True, None

        installed_display = ", ".join(sorted(installed_names)) or "none"
        return (
            False,
            f"Ollama model '{normalized_model}' is not installed locally. "
            f"Installed models: {installed_display}",
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
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
        model: str = "",
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
