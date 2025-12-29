"""
Base Compile Target Plugin interface.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any

from app.models.lens_kernel import EffectiveLens, CompiledLensContext


class CompileTarget(str, Enum):
    """Compile target types"""
    COPY = "copy"
    VISUAL = "visual"
    LAYOUT = "layout"
    NARRATIVE = "narrative"
    CODE = "code"


class CompileTargetPlugin(ABC):
    """Base class for compile target plugins"""

    @abstractmethod
    def get_target(self) -> CompileTarget:
        """Get compile target type"""
        pass

    @abstractmethod
    def compile(self, effective_lens: EffectiveLens) -> CompiledLensContext:
        """
        Compile effective lens to target-specific context

        Args:
            effective_lens: Effective lens to compile

        Returns:
            CompiledLensContext for the target
        """
        pass

