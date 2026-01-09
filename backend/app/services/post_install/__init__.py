"""
Post Install Bootstrap System

使用策略模式处理 bootstrap 操作，避免硬编码业务逻辑。
"""

from .bootstrap_registry import BootstrapRegistry
from .bootstrap_strategies import (
    BootstrapStrategy,
    PythonScriptStrategy,
    ContentVaultInitStrategy,
    SiteHubRuntimeInitStrategy,
    ConditionalBootstrapStrategy,
)

__all__ = [
    'BootstrapRegistry',
    'BootstrapStrategy',
    'PythonScriptStrategy',
    'ContentVaultInitStrategy',
    'SiteHubRuntimeInitStrategy',
    'ConditionalBootstrapStrategy',
]

