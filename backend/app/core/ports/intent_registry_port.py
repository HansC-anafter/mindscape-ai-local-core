"""
Intent Registry Port - Resolve user input to Intent
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from ..execution_context import ExecutionContext


class IntentResolutionResult(BaseModel):
    """
    Intent resolution result
    """
    intents: List[Dict[str, Any]]
    themes: List[str]
    confidence: Optional[float] = None
    llm_analysis: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {
            dict: lambda v: v
        }


class IntentDefinition(BaseModel):
    """
    Intent definition (for list_available_intents)
    """
    code: str
    label: str
    description: Optional[str] = None
    category: Optional[str] = None

    class Config:
        json_encoders = {
            dict: lambda v: v
        }


class IntentRegistryPort(ABC):
    """
    Intent Registry Port - Resolve user input to Intent
    """

    @abstractmethod
    async def resolve_intent(
        self,
        user_input: str,
        ctx: ExecutionContext,
        context: Optional[str] = None,
        locale: Optional[str] = None
    ) -> IntentResolutionResult:
        """
        Resolve user input to Intent

        Args:
            user_input: User input message
            ctx: Execution context
            context: Optional additional context (file content, timeline, etc.)
            locale: Target language

        Returns:
            IntentResolutionResult containing intents, themes, confidence, etc.
        """
        pass

    @abstractmethod
    async def list_available_intents(
        self,
        ctx: ExecutionContext
    ) -> List[IntentDefinition]:
        """
        List available Intent definitions

        Args:
            ctx: Execution context

        Returns:
            List of IntentDefinition
        """
        pass

