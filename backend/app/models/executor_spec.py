"""
ExecutorSpec — workspace 與執行器的綁定規格。

每個 workspace 可綁定多個 ExecutorSpec，調度時按 priority 逐一嘗試。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutorSpec:
    """執行器與 workspace 的綁定規格。"""

    runtime_id: str
    """Registry key（snake_case，例如 'gemini_cli'）。"""

    display_name: str = ""
    """UI 顯示名稱（例如 'Gemini CLI'）。"""

    is_primary: bool = False
    """True = 此 workspace 的預設執行器。"""

    config: Dict[str, Any] = field(default_factory=dict)
    """Workspace 專屬覆寫（timeout、allowed_tools 等）。"""

    priority: int = 0
    """調度優先順序（數字越小越優先）。"""

    # ---- 序列化 ----

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutorSpec":
        return cls(
            runtime_id=data["runtime_id"],
            display_name=data.get("display_name", ""),
            is_primary=data.get("is_primary", False),
            config=data.get("config", {}),
            priority=data.get("priority", 0),
        )


# ---- 集合層級約束驗證 ----


def validate_executor_specs(specs: List[ExecutorSpec]) -> List[str]:
    """
    驗證 ExecutorSpec 列表的約束，回傳違規訊息列表（空 = 通過）。

    約束：
    1. runtime_id 在同一 workspace 內唯一
    2. 恰好一個 is_primary = True（若列表非空）
    3. priority 不重複
    """
    errors: List[str] = []
    if not specs:
        return errors

    # 1. runtime_id 唯一
    ids = [s.runtime_id for s in specs]
    if len(ids) != len(set(ids)):
        dupes = [rid for rid in ids if ids.count(rid) > 1]
        errors.append(f"Duplicate runtime_id: {set(dupes)}")

    # 2. 恰好一個 primary
    primaries = [s for s in specs if s.is_primary]
    if len(primaries) == 0:
        errors.append("No primary executor specified")
    elif len(primaries) > 1:
        errors.append(f"Multiple primaries: {[s.runtime_id for s in primaries]}")

    # 3. priority 不重複
    prios = [s.priority for s in specs]
    if len(prios) != len(set(prios)):
        errors.append(f"Duplicate priorities: {prios}")

    return errors


def resolve_executor_chain(specs: List[ExecutorSpec]) -> List[str]:
    """
    回傳按 priority 排序的 runtime_id 列表（primary 排最前）。

    調度用：逐一嘗試直到成功，全部失敗後走 fallback_model。
    """
    if not specs:
        return []
    sorted_specs = sorted(specs, key=lambda s: (not s.is_primary, s.priority))
    return [s.runtime_id for s in sorted_specs]


def promote_next_primary(specs: List[ExecutorSpec]) -> List[ExecutorSpec]:
    """
    刪除 primary 後自動遞補：將 priority 最小的 spec 設為 primary。
    """
    if not specs:
        return specs
    if any(s.is_primary for s in specs):
        return specs
    sorted_specs = sorted(specs, key=lambda s: s.priority)
    sorted_specs[0].is_primary = True
    return specs
