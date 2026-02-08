"""
Token Estimator Module

Provides token counting utilities using tiktoken for accurate LLM token estimation.
"""

import logging
from typing import Optional

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger(__name__)


class TokenEstimator:
    """Estimates token counts for text using tiktoken"""

    def __init__(self, model_name: str):
        """
        Initialize TokenEstimator

        Args:
            model_name: Model name for encoding selection (required)
        """
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "model_name is required for TokenEstimator. "
                "Please get the model name from SystemSettingsStore and pass it explicitly."
            )
        self.model_name = model_name

    def estimate(self, text: str, model_name: Optional[str] = None) -> int:
        """
        Estimate token count for a given text using tiktoken

        Args:
            text: Text to estimate tokens for
            model_name: Model name to use for encoding (defaults to self.model_name)

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        if not TIKTOKEN_AVAILABLE:
            return len(text.split()) * 2

        try:
            effective_model = model_name or self.model_name

            if not effective_model or effective_model.strip() == "":
                raise ValueError(
                    "LLM model not configured for token estimation. "
                    "Please select a model in the system settings panel."
                )

            encoding_name = "cl100k_base"
            if (
                "gpt-4" in effective_model.lower()
                or "gpt-3.5" in effective_model.lower()
            ):
                encoding_name = "cl100k_base"
            elif "o1" in effective_model.lower() or "o3" in effective_model.lower():
                encoding_name = "o200k_base"

            encoding = tiktoken.get_encoding(encoding_name)
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(
                f"Failed to estimate token count with tiktoken: {e}, falling back to word count"
            )
            return len(text.split()) * 2
