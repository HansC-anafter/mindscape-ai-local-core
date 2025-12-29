"""
Preset Diff Service

比较两个 Preset 的差异
"""
from typing import Dict
from app.services.stores.graph_store import GraphStore
from app.models.graph import LensProfileNode, LensNodeState, GraphNode
from app.models.preset_diff import PresetDiff, NodeStateChange


class PresetDiffService:
    """Preset 差异比较服务"""

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store

    def compare(
        self,
        preset_a_id: str,
        preset_b_id: str
    ) -> PresetDiff:
        """
        比较两个 Preset 的差异

        Args:
            preset_a_id: Preset A ID
            preset_b_id: Preset B ID

        Returns:
            PresetDiff 对象
        """
        # 获取 Preset 信息
        preset_a = self.graph_store.get_lens_profile(preset_a_id)
        preset_b = self.graph_store.get_lens_profile(preset_b_id)

        if not preset_a:
            raise ValueError(f"Preset A not found: {preset_a_id}")
        if not preset_b:
            raise ValueError(f"Preset B not found: {preset_b_id}")

        # 获取节点状态
        nodes_a = self.graph_store.get_lens_profile_nodes(preset_a_id)
        nodes_b = self.graph_store.get_lens_profile_nodes(preset_b_id)

        # 转换为字典便于查找
        states_a: Dict[str, LensNodeState] = {pn.node_id: pn.state for pn in nodes_a}
        states_b: Dict[str, LensNodeState] = {pn.node_id: pn.state for pn in nodes_b}

        # 找出所有涉及的节点（并集）
        all_node_ids = set(states_a.keys()) | set(states_b.keys())

        # 计算差异
        changes = []
        for node_id in all_node_ids:
            state_a = states_a.get(node_id, LensNodeState.KEEP)
            state_b = states_b.get(node_id, LensNodeState.KEEP)

            # 如果状态相同，跳过
            if state_a == state_b:
                continue

            # 获取节点信息
            # get_node 方法只需要 node_id，不需要 profile_id
            node = self.graph_store.get_node(node_id)
            if not node:
                # 如果节点不存在，跳过（可能已被删除）
                logger.warning(f"Node {node_id} not found, skipping diff")
                continue

            change_type = self._classify_change(state_a, state_b)
            changes.append(NodeStateChange(
                node_id=node_id,
                node_label=node.label,
                node_type=node.node_type.value,
                category=node.category.value,
                from_state=state_a,
                to_state=state_b,
                change_type=change_type
            ))

        return PresetDiff(
            preset_a_id=preset_a_id,
            preset_a_name=preset_a.name,
            preset_b_id=preset_b_id,
            preset_b_name=preset_b.name,
            changes=changes
        )

    def _classify_change(
        self,
        from_state: LensNodeState,
        to_state: LensNodeState
    ) -> str:
        """
        分类变化类型

        Returns:
            'strengthened': 强化（off → keep, keep → emphasize, off → emphasize）
            'weakened': 弱化（emphasize → keep, keep → off, emphasize → off）
            'disabled': 关闭（任何 → off）
            'enabled': 启用（off → keep/emphasize）
            'changed': 其他变化
        """
        if to_state == LensNodeState.OFF:
            return 'disabled'
        elif from_state == LensNodeState.OFF:
            return 'enabled'
        elif (from_state == LensNodeState.KEEP and
              to_state == LensNodeState.EMPHASIZE):
            return 'strengthened'
        elif (from_state == LensNodeState.EMPHASIZE and
              to_state == LensNodeState.KEEP):
            return 'weakened'
        elif (from_state == LensNodeState.OFF and
              to_state == LensNodeState.EMPHASIZE):
            return 'strengthened'
        elif (from_state == LensNodeState.EMPHASIZE and
              to_state == LensNodeState.OFF):
            return 'weakened'
        else:
            return 'changed'

