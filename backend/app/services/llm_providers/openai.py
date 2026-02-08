"""
OpenAI LLM Provider
"""

from typing import Dict, List, Optional
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI API provider"""

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str:
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=self.api_key)

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }

            # For newer models (like gpt-5.1, o1, o3), use max_completion_tokens via extra_body
            # SDK 1.3.7 doesn't have max_completion_tokens in signature, but API supports it
            model_lower = model.lower() if model else ""
            is_newer_model = (
                "gpt-5" in model_lower or "o1" in model_lower or "o3" in model_lower
            )

            if is_newer_model:
                # For newer models, use max_completion_tokens via extra_body
                # SDK 1.3.7 doesn't support it directly, but API does
                # Newer models (gpt-5.x, o1, o3) support higher token limits
                token_param = (
                    max_completion_tokens
                    if max_completion_tokens is not None
                    else max_tokens
                )
                if token_param is not None:
                    # Use extra_body to pass max_completion_tokens (SDK 1.3.7 workaround)
                    if "extra_body" not in request_params:
                        request_params["extra_body"] = {}
                    request_params["extra_body"]["max_completion_tokens"] = token_param
                    logger.info(
                        f"Using max_completion_tokens={token_param} via extra_body for {model}"
                    )
                else:
                    # Default to higher limit for newer models (they support it)
                    if "extra_body" not in request_params:
                        request_params["extra_body"] = {}
                    request_params["extra_body"]["max_completion_tokens"] = 8000
                    logger.info(f"Using default max_completion_tokens=8000 for {model}")
                # Don't set max_tokens for newer models (API will reject it)
            else:
                # Older models use max_tokens
                # Older models (gpt-3.5-turbo, gpt-4o-mini) have lower limits, cap at 4096
                if max_tokens is not None:
                    # Cap at 4096 for older models (safety limit)
                    request_params["max_tokens"] = min(max_tokens, 4096)
                else:
                    # Default to 4096 for older models (safe default, prevents model limit errors)
                    request_params["max_tokens"] = 4096

            # Handle streaming vs non-streaming
            if stream:
                # Streaming mode - collect chunks
                request_params["stream"] = True
                stream = await client.chat.completions.create(**request_params)

                full_text = ""
                async for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            full_text += delta.content

                logger.info(f"LLM streaming response received: {len(full_text)} chars")
                return full_text
            else:
                # Non-streaming mode
                response = await client.chat.completions.create(**request_params)

                # Extract response text
                response_text = None
                if response.choices and len(response.choices) > 0:
                    message = response.choices[0].message
                    if hasattr(message, "content"):
                        response_text = message.content

                # Log response for debugging
                if response_text:
                    logger.info(
                        f"LLM response received: {len(response_text)} chars, preview: {response_text[:100]}"
                    )
                else:
                    logger.warning(
                        f"LLM response is empty or None. Response object: {response}"
                    )
                    logger.warning(
                        f"Response choices: {response.choices if hasattr(response, 'choices') else 'N/A'}"
                    )
                    if (
                        hasattr(response, "choices")
                        and response.choices
                        and len(response.choices) > 0
                    ):
                        logger.warning(f"First choice: {response.choices[0]}")
                        if hasattr(response.choices[0], "message"):
                            logger.warning(
                                f"First choice message: {response.choices[0].message}"
                            )
                            if hasattr(response.choices[0].message, "content"):
                                logger.warning(
                                    f"First choice message content: {response.choices[0].message.content}"
                                )

                return response_text or ""

        except ImportError:
            raise Exception("OpenAI package not installed")
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        """
        Streaming chat completion - returns stream object for SSE

        Returns:
            AsyncGenerator that yields chunks from OpenAI stream
        """
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=self.api_key)

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }

            # Handle token limits for different model types
            model_lower = model.lower() if model else ""
            is_newer_model = (
                "gpt-5" in model_lower or "o1" in model_lower or "o3" in model_lower
            )

            if is_newer_model:
                # For newer models, use max_completion_tokens via extra_body
                token_param = (
                    max_completion_tokens
                    if max_completion_tokens is not None
                    else max_tokens
                )
                if token_param is not None:
                    if "extra_body" not in request_params:
                        request_params["extra_body"] = {}
                    request_params["extra_body"]["max_completion_tokens"] = token_param
                else:
                    if "extra_body" not in request_params:
                        request_params["extra_body"] = {}
                    request_params["extra_body"]["max_completion_tokens"] = 8000
            else:
                # Older models use max_tokens
                if max_tokens is not None:
                    request_params["max_tokens"] = min(max_tokens, 4096)
                else:
                    request_params["max_tokens"] = 4096

            # Create and return stream
            stream = await client.chat.completions.create(**request_params)
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        yield delta.content
        except ImportError:
            raise Exception("OpenAI package not installed")
        except Exception as e:
            logger.error(f"OpenAI streaming API error: {e}", exc_info=True)
            raise
