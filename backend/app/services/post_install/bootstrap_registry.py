"""
Bootstrap Strategy Registry

注册和管理所有 bootstrap 策略
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
    """Bootstrap 策略注册表"""

    _instance: Optional['BootstrapRegistry'] = None
    _strategies: Dict[str, BootstrapStrategy] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初始化默认策略"""
        if not self._strategies:
            # 注册默认策略
            self.register(PythonScriptStrategy())
            self.register(ContentVaultInitStrategy())
            self.register(SiteHubRuntimeInitStrategy())
            self.register(ConditionalBootstrapStrategy())

    def register(self, strategy: BootstrapStrategy):
        """注册一个策略"""
        strategy_type = strategy.get_type()
        self._strategies[strategy_type] = strategy
        logger.debug(f"Registered bootstrap strategy: {strategy_type}")

    def get_strategy(self, strategy_type: str) -> Optional[BootstrapStrategy]:
        """获取策略"""
        return self._strategies.get(strategy_type)

    def list_strategies(self) -> list:
        """列出所有已注册的策略类型"""
        return list(self._strategies.keys())

