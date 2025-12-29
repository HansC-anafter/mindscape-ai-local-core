"""
Orchestrator Registry - 全局 Orchestrator 註冊表

用於在執行過程中存儲和獲取 MultiAgentOrchestrator 實例。
ToolExecutor 可以通過 execution_id 獲取 orchestrator 來記錄 tool calls。
"""

from typing import Dict, Optional
from backend.app.services.orchestration.multi_agent_orchestrator import MultiAgentOrchestrator
import logging

logger = logging.getLogger(__name__)


class OrchestratorRegistry:
    """全局 Orchestrator 註冊表（單例）"""

    _instance: Optional['OrchestratorRegistry'] = None
    _orchestrators: Dict[str, MultiAgentOrchestrator] = {}  # execution_id -> orchestrator

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, execution_id: str, orchestrator: MultiAgentOrchestrator):
        """註冊 orchestrator"""
        self._orchestrators[execution_id] = orchestrator
        logger.debug(f"OrchestratorRegistry: Registered orchestrator for execution_id={execution_id}")

    def get(self, execution_id: str) -> Optional[MultiAgentOrchestrator]:
        """獲取 orchestrator"""
        return self._orchestrators.get(execution_id)

    def find_by_any_key(self, *keys: str) -> Optional[MultiAgentOrchestrator]:
        """
        嘗試使用多個鍵查找 orchestrator（fallback 機制）

        Args:
            *keys: 多個可能的鍵（按優先順序）

        Returns:
            第一個找到的 orchestrator，或 None
        """
        for key in keys:
            if key and key in self._orchestrators:
                logger.debug(f"OrchestratorRegistry: Found orchestrator using fallback key={key}")
                return self._orchestrators[key]
        return None

    def find_any(self) -> Optional[MultiAgentOrchestrator]:
        """
        查找任何已註冊的 orchestrator（最後手段 fallback）

        注意：這應該只在無法確定正確鍵時使用，因為可能返回錯誤的 orchestrator

        Returns:
            第一個找到的 orchestrator，或 None
        """
        if self._orchestrators:
            # 返回最近註冊的（最後一個）
            orchestrator = list(self._orchestrators.values())[-1]
            logger.warning(
                f"OrchestratorRegistry: Using fallback 'find_any' - found {len(self._orchestrators)} registered orchestrators. "
                f"This may return incorrect orchestrator if multiple executions are running."
            )
            return orchestrator
        return None

    def unregister(self, execution_id: str):
        """取消註冊 orchestrator"""
        if execution_id in self._orchestrators:
            del self._orchestrators[execution_id]
            logger.debug(f"OrchestratorRegistry: Unregistered orchestrator for execution_id={execution_id}")

    def unregister_by_orchestrator(self, orchestrator: MultiAgentOrchestrator):
        """
        通過 orchestrator 實例取消註冊所有相關的鍵

        用於清理：當同一個 orchestrator 被多個鍵註冊時，一次性清理所有
        """
        keys_to_remove = [
            key for key, value in self._orchestrators.items()
            if value is orchestrator
        ]
        for key in keys_to_remove:
            del self._orchestrators[key]
        if keys_to_remove:
            logger.debug(f"OrchestratorRegistry: Unregistered orchestrator from {len(keys_to_remove)} keys: {keys_to_remove}")

    def clear(self):
        """清空所有註冊的 orchestrator（用於測試）"""
        self._orchestrators.clear()


# 全局實例
_orchestrator_registry = OrchestratorRegistry()


def get_orchestrator_registry() -> OrchestratorRegistry:
    """獲取全局 OrchestratorRegistry 實例"""
    return _orchestrator_registry

