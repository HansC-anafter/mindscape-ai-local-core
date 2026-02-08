"""
Google Vertex AI LLM Provider
"""

import asyncio
import sys
from typing import Dict, List, Optional
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)


class VertexAIProvider(LLMProvider):
    """Google Vertex AI provider"""

    def __init__(
        self,
        api_key: str,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """
        Initialize Vertex AI provider

        Args:
            api_key: Service Account JSON string or path to JSON file
            project_id: GCP Project ID (optional, can be in api_key JSON)
            location: Vertex AI location (default: us-central1)
        """
        super().__init__(api_key)
        self.project_id = project_id
        self.location = location or "us-central1"
        self._initialized = False
        self._model_instance_cache = {}

    def _ensure_initialized(self):
        """Initialize Vertex AI platform if not already initialized"""
        if self._initialized:
            return

        import json
        from google.oauth2 import service_account
        from google.cloud import aiplatform

        credentials = None
        if self.api_key:
            try:
                sa_info = json.loads(self.api_key)
                credentials = service_account.Credentials.from_service_account_info(
                    sa_info
                )
                if not self.project_id and "project_id" in sa_info:
                    self.project_id = sa_info["project_id"]
            except (json.JSONDecodeError, ValueError):
                credentials = service_account.Credentials.from_service_account_file(
                    self.api_key
                )
                if not self.project_id:
                    with open(self.api_key, "r") as f:
                        sa_info = json.load(f)
                        if "project_id" in sa_info:
                            self.project_id = sa_info["project_id"]

        if credentials:
            aiplatform.init(
                project=self.project_id, location=self.location, credentials=credentials
            )
        else:
            aiplatform.init(project=self.project_id, location=self.location)

        self._initialized = True

    def _prepare_messages(self, messages: List[Dict[str, str]]):
        """Convert standard message format to Vertex AI format"""
        vertex_messages = []
        system_instruction = None

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                vertex_messages.append(
                    {"role": "user", "parts": [{"text": msg["content"]}]}
                )
            elif msg["role"] == "assistant":
                vertex_messages.append(
                    {"role": "model", "parts": [{"text": msg["content"]}]}
                )

        return vertex_messages, system_instruction

    def _get_model_instance(self, model: str, system_instruction: Optional[str] = None):
        """Get or create model instance with optional system instruction"""
        # [Fallback Remapping] Map generic/OpenAI model names to Gemini equivalents
        # This handles cases where system defaults (gpt-4o-mini) are passed to Vertex provider
        if model and ("gpt" in model.lower() or "openai" in model.lower()):
            original_model = model
            model = "gemini-2.0-flash"  # Updated from deprecated gemini-1.5-flash-001
            logger.info(
                f"VertexAIProvider: Remapping requested model '{original_model}' to '{model}'"
            )

        cache_key = f"{model}:{system_instruction}" if system_instruction else model
        if cache_key not in self._model_instance_cache:
            try:
                from vertexai.generative_models import GenerativeModel
            except ImportError:
                from vertexai.preview.generative_models import GenerativeModel
            if system_instruction:
                self._model_instance_cache[cache_key] = GenerativeModel(
                    model_name=model, system_instruction=system_instruction
                )
            else:
                self._model_instance_cache[cache_key] = GenerativeModel(
                    model_name=model
                )
        return self._model_instance_cache[cache_key]

    def _build_generation_config(
        self,
        temperature: float,
        max_tokens: Optional[int],
        max_completion_tokens: Optional[int],
    ):
        """Build generation config for Vertex AI"""
        from vertexai.generative_models import GenerationConfig

        # Increase max_output_tokens to prevent truncation (Gemini models support up to 8192)
        # Use max_completion_tokens if provided, otherwise max_tokens, otherwise default to 2000 for welcome messages
        max_output = (
            max_completion_tokens
            if max_completion_tokens
            else (max_tokens if max_tokens else 2000)
        )
        # Cap at 8192 for Gemini models, but ensure minimum of 1000 for proper completion
        max_output = min(max(max_output, 1000), 8192)

        logger.info(
            f"Vertex AI GenerationConfig: max_output_tokens={max_output}, temperature={temperature}, max_tokens={max_tokens}, max_completion_tokens={max_completion_tokens}"
        )
        print(
            f"[DEBUG] Vertex AI GenerationConfig: max_output_tokens={max_output}, temperature={temperature}, max_tokens={max_tokens}, max_completion_tokens={max_completion_tokens}",
            file=sys.stderr,
        )
        config = GenerationConfig(temperature=temperature, max_output_tokens=max_output)
        # Store max_output on the config object for later retrieval
        config._actual_max_output_tokens = max_output
        return config

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-pro",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str:
        try:
            self._ensure_initialized()
            vertex_messages, system_instruction = self._prepare_messages(messages)
            model_instance = self._get_model_instance(model, system_instruction)
            generation_config = self._build_generation_config(
                temperature, max_tokens, max_completion_tokens
            )

            response = await model_instance.generate_content_async(
                contents=vertex_messages, generation_config=generation_config
            )

            # Extract and log usage metadata if available
            if hasattr(response, "usage_metadata"):
                usage = response.usage_metadata
                logger.info(
                    f"Vertex AI usage_metadata: prompt_token_count={getattr(usage, 'prompt_token_count', 'N/A')}, "
                    f"candidates_token_count={getattr(usage, 'candidates_token_count', 'N/A')}, "
                    f"total_token_count={getattr(usage, 'total_token_count', 'N/A')}"
                )

                print(
                    f"[DEBUG] usage_metadata: prompt={getattr(usage, 'prompt_token_count', 'N/A')}, candidates={getattr(usage, 'candidates_token_count', 'N/A')}, total={getattr(usage, 'total_token_count', 'N/A')}",
                    file=sys.stderr,
                )

            # Handle multi-part responses (Vertex AI may return multiple content parts)
            # This fixes "Multiple content parts are not supported" error
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                # Log finish reason for debugging
                if hasattr(candidate, "finish_reason"):
                    logger.info(f"Vertex AI finish_reason: {candidate.finish_reason}")

                    # Read max_output_tokens from stored attribute
                    max_output_val = getattr(
                        generation_config, "_actual_max_output_tokens", "N/A"
                    )
                    # Get actual output token count from usage_metadata
                    actual_output_tokens = "N/A"
                    prompt_tokens = "N/A"
                    total_tokens = "N/A"
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        actual_output_tokens = getattr(
                            response.usage_metadata, "candidates_token_count", "N/A"
                        )
                        prompt_tokens = getattr(
                            response.usage_metadata, "prompt_token_count", "N/A"
                        )
                        total_tokens = getattr(
                            response.usage_metadata, "total_token_count", "N/A"
                        )

                    # Get finish_reason enum name
                    from vertexai.generative_models import FinishReason

                    finish_reason_name = "UNKNOWN"
                    try:
                        finish_reason_name = FinishReason(candidate.finish_reason).name
                    except:
                        finish_reason_name = str(candidate.finish_reason)

                    print(
                        f"[DEBUG] finish_reason: {candidate.finish_reason} ({finish_reason_name}), max_output_tokens={max_output_val}, prompt_tokens={prompt_tokens}, output_tokens={actual_output_tokens}, total_tokens={total_tokens}",
                        file=sys.stderr,
                    )

                    # If finish_reason=2 but output_tokens is much lower than max_output_tokens, log warning
                    if (
                        candidate.finish_reason == 2
                        and max_output_val != "N/A"
                        and actual_output_tokens != "N/A"
                    ):
                        if isinstance(max_output_val, int) and isinstance(
                            actual_output_tokens, int
                        ):
                            if (
                                actual_output_tokens < max_output_val * 0.5
                            ):  # If actual output is less than 50% of set value
                                print(
                                    f"[WARNING] finish_reason=2 but output_tokens ({actual_output_tokens}) is much lower than max_output_tokens ({max_output_val}), may be triggered by other limits (safety filter, thinking budget, etc.)",
                                    file=sys.stderr,
                                )

                    if (
                        candidate.finish_reason and candidate.finish_reason != 1
                    ):  # 1 = STOP (normal completion)
                        logger.warning(
                            f"Vertex AI response finished with reason: {candidate.finish_reason} (1=STOP, 2=MAX_TOKENS, 3=SAFETY)"
                        )

                if candidate.content and candidate.content.parts:
                    # Concatenate all text parts
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        full_text = "".join(text_parts)
                        logger.info(f"Vertex AI returned {len(full_text)} characters")
                        return full_text

            # Fallback to response.text (may raise error if multi-part)
            try:
                return response.text
            except Exception as text_error:
                logger.warning(
                    f"Vertex AI response.text failed: {text_error}, attempting manual extraction"
                )
                # Last resort: try to get any text from the response
                if hasattr(response, "candidates") and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, "content") and candidate.content:
                            if (
                                hasattr(candidate.content, "parts")
                                and candidate.content.parts
                            ):
                                texts = [
                                    p.text
                                    for p in candidate.content.parts
                                    if hasattr(p, "text") and p.text
                                ]
                                if texts:
                                    return "".join(texts)
                raise text_error

        except ImportError:
            raise Exception(
                "Google Cloud AI Platform or Vertex AI packages not installed. Install with: pip install google-cloud-aiplatform vertexai"
            )
        except Exception as e:
            logger.error(f"Vertex AI API error: {e}")
            raise

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gemini-pro",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        """
        Streaming chat completion - returns async generator for SSE

        Returns:
            AsyncGenerator that yields chunks from Vertex AI stream
        """
        try:
            self._ensure_initialized()
            vertex_messages, system_instruction = self._prepare_messages(messages)
            model_instance = self._get_model_instance(model, system_instruction)
            generation_config = self._build_generation_config(
                temperature, max_tokens, max_completion_tokens
            )

            def create_stream():
                return model_instance.generate_content(
                    contents=vertex_messages,
                    generation_config=generation_config,
                    stream=True,
                )

            responses = await asyncio.to_thread(create_stream)
            for response in responses:
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    # Check for finish_reason to detect truncation
                    if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                        finish_reason = candidate.finish_reason
                        if (
                            finish_reason == 1
                        ):  # STOP = 1 (normal completion), MAX_TOKENS = 2, SAFETY = 3, RECITATION = 4
                            # Finish reason 1 is STOP (normal completion), not an error
                            logger.debug(
                                f"[VertexAI Streaming] Response completed normally. Finish reason: {finish_reason} (STOP)"
                            )
                        elif finish_reason == 2:  # MAX_TOKENS
                            logger.warning(
                                f"[VertexAI Streaming] Response truncated due to max_tokens limit. Finish reason: {finish_reason}"
                            )
                        elif finish_reason == 3:  # SAFETY
                            logger.warning(
                                f"[VertexAI Streaming] Response stopped due to safety filter. Finish reason: {finish_reason}"
                            )
                        else:
                            logger.warning(
                                f"[VertexAI Streaming] Response stopped with unexpected reason. Finish reason: {finish_reason}"
                            )
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                yield part.text
                                await asyncio.sleep(0)

        except ImportError:
            raise Exception(
                "Google Cloud AI Platform or Vertex AI packages not installed. Install with: pip install google-cloud-aiplatform vertexai"
            )
        except Exception as e:
            logger.error(f"Vertex AI streaming API error: {e}", exc_info=True)
            raise
