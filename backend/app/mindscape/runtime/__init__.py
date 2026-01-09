"""
Mindscape Runtime

運行時支援模組，包括：
- 降級狀態管理
- 功能可用性檢查
- 環境適配
"""

from .degradation import (
    DegradationRegistry,
    CapabilityStatus,
    get_capability_status,
    is_feature_available,
)

__all__ = [
    "DegradationRegistry",
    "CapabilityStatus",
    "get_capability_status",
    "is_feature_available",
]



