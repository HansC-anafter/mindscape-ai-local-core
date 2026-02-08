"""
LlamaCpp Local LLM Provider (GGUF models with Metal support)
"""

import asyncio
from typing import Dict, List
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)


class LlamaCppProvider(LLMProvider):
    """Local GGUF provider using llama.cpp / metal"""

    def __init__(self, model_path: str, n_ctx: int = 4096):
        super().__init__(api_key="local")
        self.model_path = model_path
        self.n_ctx = n_ctx
        self._llm = None

    def _ensure_model_loaded(self):
        if self._llm:
            return
        try:
            import llama_cpp

            logger.info(
                f"Loading local GGUF model from {self.model_path} (Metal enabled)"
            )
            self._llm = llama_cpp.Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_gpu_layers=-1,  # Use all layers on Apple Silicon (MPS/Metal)
                verbose=False,
            )
        except ImportError:
            logger.error(
                "llama-cpp-python not installed. Use CMAKE_ARGS='-DLLAMA_METAL=on' to install."
            )
            raise Exception("llama-cpp-python not installed for local preview.")

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        self._ensure_model_loaded()

        # Simple ChatML-like formatting for Llama-3 / GGUF
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"

        # Offload execution to thread to avoid blocking event loop
        loop = asyncio.get_event_loop()

        def _run():
            return self._llm(
                prompt,
                max_tokens=kwargs.get("max_tokens", 1024),
                stop=["<|im_end|>", "user:", "assistant:"],
                echo=False,
            )

        response = await loop.run_in_executor(None, _run)
        return response["choices"][0]["text"].strip()

    async def chat_completion_stream(self, messages: List[Dict[str, str]], **kwargs):
        # Placeholder for streaming
        text = await self.chat_completion(messages, **kwargs)
        yield text
