"""
Bootstrap Strategy Registry

Registers and manages all bootstrap strategies.
"""

import logging
from typing import Dict, Optional

from .bootstrap_strategies import (
    BootstrapStrategy,
    PythonScriptStrategy,
    ContentVaultInitStrategy,
    SiteHubRuntimeInitStrategy,
    ConditionalBootstrapStrategy,
)

logger = logging.getLogger(__name__)


class BootstrapRegistry:
    """Bootstrap strategy registry"""

    _instance: Optional['BootstrapRegistry'] = None
    _strategies: Dict[str, BootstrapStrategy] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize default strategies"""
        if not self._strategies:
            self.register(PythonScriptStrategy())
            self.register(ContentVaultInitStrategy())
            self.register(SiteHubRuntimeInitStrategy())
            self.register(ConditionalBootstrapStrategy())

    def register(self, strategy: BootstrapStrategy):
        """Register a strategy"""
        strategy_type = strategy.get_type()
        self._strategies[strategy_type] = strategy
        logger.debug(f"Registered bootstrap strategy: {strategy_type}")

    def get_strategy(self, strategy_type: str) -> Optional[BootstrapStrategy]:
        """Get strategy by type"""
        return self._strategies.get(strategy_type)

    def list_strategies(self) -> list:
        """List all registered strategy types"""
        return list(self._strategies.keys())

