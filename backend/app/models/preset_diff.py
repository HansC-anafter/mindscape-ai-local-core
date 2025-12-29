"""
Preset Diff Models

用于比较两个 Preset 之间的差异
"""
from typing import List, Literal
from pydantic import BaseModel, Field
from app.models.graph import LensNodeState


class NodeStateChange(BaseModel):
    """单个节点的状态变化"""
    node_id: str = Field(..., description="节点 ID")
    node_label: str = Field(..., description="节点标签")
    node_type: str = Field(..., description="节点类型")
    category: str = Field(..., description="节点分类")
    from_state: LensNodeState = Field(..., description="原始状态")
    to_state: LensNodeState = Field(..., description="目标状态")
    change_type: Literal['strengthened', 'weakened', 'disabled', 'enabled', 'changed'] = Field(
        ..., description="变化类型"
    )


class PresetDiff(BaseModel):
    """两个 Preset 之间的差异"""
    preset_a_id: str = Field(..., description="Preset A ID")
    preset_a_name: str = Field(..., description="Preset A 名称")
    preset_b_id: str = Field(..., description="Preset B ID")
    preset_b_name: str = Field(..., description="Preset B 名称")
    changes: List[NodeStateChange] = Field(default_factory=list, description="变化列表")

    @property
    def strengthened_count(self) -> int:
        """强化节点数量"""
        return len([c for c in self.changes if c.change_type == 'strengthened'])

    @property
    def weakened_count(self) -> int:
        """弱化节点数量"""
        return len([c for c in self.changes if c.change_type == 'weakened'])

    @property
    def disabled_count(self) -> int:
        """关闭节点数量"""
        return len([c for c in self.changes if c.change_type == 'disabled'])

    @property
    def enabled_count(self) -> int:
        """启用节点数量"""
        return len([c for c in self.changes if c.change_type == 'enabled'])

    def get_summary(self) -> str:
        """生成人类可读的摘要"""
        parts = []
        if self.strengthened_count > 0:
            parts.append(f"強化 {self.strengthened_count} 個節點")
        if self.weakened_count > 0:
            parts.append(f"弱化 {self.weakened_count} 個節點")
        if self.disabled_count > 0:
            parts.append(f"關閉 {self.disabled_count} 個節點")
        if self.enabled_count > 0:
            parts.append(f"啟用 {self.enabled_count} 個節點")

        return "、".join(parts) if parts else "無差異"

