"""
Post Install Bootstrap System

Uses strategy pattern to handle bootstrap operations, avoiding hardcoded business logic.
"""

from .bootstrap_registry import BootstrapRegistry
from .bootstrap_strategies import (
    BootstrapStrategy,
    PythonScriptStrategy,
    ContentVaultInitStrategy,
    CloudProviderRuntimeInitStrategy,
    ConditionalBootstrapStrategy,
)

__all__ = [
    "BootstrapRegistry",
    "BootstrapStrategy",
    "PythonScriptStrategy",
    "ContentVaultInitStrategy",
    "CloudProviderRuntimeInitStrategy",
    "ConditionalBootstrapStrategy",
]
