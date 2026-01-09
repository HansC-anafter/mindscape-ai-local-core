"""
Runtime Degradation Registry

管理 capability 的運行時降級狀態。

當可選依賴不可用時，capability 可以在降級模式下運行，
部分功能不可用但核心功能仍然正常。
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class CapabilityStatus:
    """Capability 運行時狀態"""
    code: str
    status: str  # "healthy" | "degraded" | "unavailable"
    available_features: List[str] = field(default_factory=list)
    degraded_features: List[str] = field(default_factory=list)
    unavailable_features: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {
            "code": self.code,
            "status": self.status,
            "available_features": self.available_features,
            "degraded_features": self.degraded_features,
            "unavailable_features": self.unavailable_features,
            "missing_dependencies": self.missing_dependencies,
        }


class DegradationRegistry:
    """
    全局降級狀態註冊表

    使用單例模式，確保全局只有一個實例。

    使用方式：
        registry = DegradationRegistry()

        # 註冊 capability 狀態
        registry.register_capability(
            code="yogacoach",
            all_features=["pipeline", "qa", "billing"],
            missing_deps=["line_messaging_api"],
            degraded_features_map={
                "line_messaging_api": ["line_push"]
            }
        )

        # 檢查功能可用性
        if registry.is_feature_available("yogacoach", "pipeline"):
            run_pipeline()
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._capabilities: Dict[str, CapabilityStatus] = {}
                    cls._instance._initialized = True
        return cls._instance

    def register_capability(
        self,
        code: str,
        all_features: List[str],
        missing_deps: List[str],
        degraded_features_map: Dict[str, List[str]]
    ) -> CapabilityStatus:
        """
        註冊 capability 狀態

        Args:
            code: Capability 代碼
            all_features: 所有功能列表
            missing_deps: 缺失的依賴列表
            degraded_features_map: 依賴 -> 降級功能列表的映射

        Returns:
            CapabilityStatus
        """
        # 計算哪些功能因為缺少依賴而降級
        degraded_features: Set[str] = set()
        for dep in missing_deps:
            features = degraded_features_map.get(dep, [])
            degraded_features.update(features)

        available = [f for f in all_features if f not in degraded_features]

        # 確定狀態
        if len(degraded_features) == 0:
            status = "healthy"
        elif len(degraded_features) == len(all_features):
            status = "unavailable"
        else:
            status = "degraded"

        cap_status = CapabilityStatus(
            code=code,
            status=status,
            available_features=available,
            degraded_features=list(degraded_features),
            missing_dependencies=missing_deps
        )

        self._capabilities[code] = cap_status

        if status == "degraded":
            logger.warning(
                f"Capability '{code}' running in degraded mode. "
                f"Degraded features: {list(degraded_features)}. "
                f"Missing dependencies: {missing_deps}"
            )
        elif status == "unavailable":
            logger.error(
                f"Capability '{code}' is unavailable. "
                f"Missing dependencies: {missing_deps}"
            )
        else:
            logger.info(f"Capability '{code}' registered as healthy")

        return cap_status

    def get_status(self, code: str) -> Optional[CapabilityStatus]:
        """
        獲取 capability 狀態

        Args:
            code: Capability 代碼

        Returns:
            CapabilityStatus 或 None
        """
        return self._capabilities.get(code)

    def get_all_statuses(self) -> Dict[str, CapabilityStatus]:
        """獲取所有 capability 狀態"""
        return self._capabilities.copy()

    def is_feature_available(self, capability_code: str, feature: str) -> bool:
        """
        檢查某個功能是否可用

        Args:
            capability_code: Capability 代碼
            feature: 功能名稱

        Returns:
            True 如果功能可用
        """
        status = self._capabilities.get(capability_code)
        if not status:
            # 未註冊的 capability，假設功能可用
            return True
        return feature in status.available_features

    def is_capability_healthy(self, code: str) -> bool:
        """
        檢查 capability 是否健康

        Args:
            code: Capability 代碼

        Returns:
            True 如果健康
        """
        status = self._capabilities.get(code)
        if not status:
            return True
        return status.status == "healthy"

    def is_capability_available(self, code: str) -> bool:
        """
        檢查 capability 是否可用（包括降級模式）

        Args:
            code: Capability 代碼

        Returns:
            True 如果可用
        """
        status = self._capabilities.get(code)
        if not status:
            return True
        return status.status in ("healthy", "degraded")

    def clear(self):
        """清除所有狀態（主要用於測試）"""
        self._capabilities.clear()


# 便捷函數
def get_capability_status(code: str) -> Optional[CapabilityStatus]:
    """獲取 capability 狀態"""
    return DegradationRegistry().get_status(code)


def is_feature_available(capability_code: str, feature: str) -> bool:
    """檢查功能是否可用"""
    return DegradationRegistry().is_feature_available(capability_code, feature)



