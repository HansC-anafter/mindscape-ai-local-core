"""
Mind-Lens Chat Service

处理三种模式的 AI 对话：
- mirror: 看見自己
- experiment: 調色實驗
- writeback: 寫回 Workspace
"""
import logging
from typing import Optional, List, Dict, Any
from app.services.lens.effective_lens_resolver import EffectiveLensResolver
from app.services.lens.session_override_store import SessionOverrideStore
from app.models.lens_kernel import EffectiveLens

logger = logging.getLogger(__name__)


class MindscapeChatService:
    """Mind-Lens Chat Service"""

    def __init__(
        self,
        resolver: EffectiveLensResolver,
        session_store: SessionOverrideStore
    ):
        self.resolver = resolver
        self.session_store = session_store

    def handle_message(
        self,
        mode: str,
        message: str,
        profile_id: str,
        workspace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        effective_lens: Optional[Dict[str, Any]] = None,
        selected_node_ids: List[str] = None
    ) -> str:
        """
        处理聊天消息

        Args:
            mode: 'mirror' | 'experiment' | 'writeback'
            message: 用户消息
            profile_id: Profile ID
            workspace_id: Optional workspace ID
            session_id: Optional session ID
            effective_lens: Optional effective lens data
            selected_node_ids: Optional selected node IDs

        Returns:
            AI 响应文本
        """
        if mode == 'mirror':
            return self._handle_mirror(message, effective_lens, selected_node_ids)
        elif mode == 'experiment':
            return self._handle_experiment(message, profile_id, workspace_id, session_id, effective_lens)
        elif mode == 'writeback':
            return self._handle_writeback(message, profile_id, workspace_id, session_id)
        else:
            return f"未知的模式: {mode}"

    def _handle_mirror(
        self,
        message: str,
        effective_lens: Optional[Dict[str, Any]],
        selected_node_ids: List[str]
    ) -> str:
        """处理 Mirror 模式消息"""
        if not effective_lens:
            return "目前沒有有效的 Lens 配置。"

        # 解析消息意图
        message_lower = message.lower()

        # 总结 Preset 核心气质
        if any(keyword in message_lower for keyword in ['總結', '核心', '氣質', '特點', '特色']):
            nodes = effective_lens.get('nodes', [])
            emphasized = [n for n in nodes if n.get('state') == 'emphasize']
            keep = [n for n in nodes if n.get('state') == 'keep']

            response = f"目前這個 Preset「{effective_lens.get('global_preset_name', 'Unknown')}」的核心特質：\n\n"
            if emphasized:
                response += f"**強調的節點 ({len(emphasized)} 個)**：\n"
                for node in emphasized[:5]:
                    response += f"- {node.get('node_label', 'Unknown')} ({node.get('node_type', 'unknown')})\n"
            if keep:
                response += f"\n**保持的節點 ({len(keep)} 個)**：\n"
                for node in keep[:5]:
                    response += f"- {node.get('node_label', 'Unknown')}\n"

            return response

        # 查看节点例子
        if any(keyword in message_lower for keyword in ['例子', '具體', '實例', '證據']):
            if selected_node_ids:
                return f"正在查詢節點 {selected_node_ids[0]} 的具體例子...\n\n（此功能需要整合 Evidence Service）"
            else:
                return "請先選擇一個節點，然後詢問它的具體例子。"

        # 查看影响最大的节点
        if any(keyword in message_lower for keyword in ['影響', '最大', '重要', '關鍵']):
            nodes = effective_lens.get('nodes', [])
            emphasized = [n for n in nodes if n.get('state') == 'emphasize']
            if emphasized:
                return f"目前影響最大的節點是「{emphasized[0].get('node_label', 'Unknown')}」，它被設定為強調狀態。"
            else:
                return "目前沒有特別強調的節點。"

        # 默认响应
        return f"我理解你想了解「{message}」。\n\n目前 Preset「{effective_lens.get('global_preset_name', 'Unknown')}」包含 {len(effective_lens.get('nodes', []))} 個節點。\n\n你可以問我：\n- 總結這個 Preset 的核心氣質\n- 某個節點的具體例子\n- 哪些節點影響最大"

    def _handle_experiment(
        self,
        message: str,
        profile_id: str,
        workspace_id: Optional[str],
        session_id: Optional[str],
        effective_lens: Optional[Dict[str, Any]]
    ) -> str:
        """处理 Experiment 模式消息"""
        # 解析实验指令
        message_lower = message.lower()

        # 检查是否包含节点调整指令
        if any(keyword in message_lower for keyword in ['關掉', '關閉', '關', 'off']):
            # 提取节点名称
            # 简单实现：提示用户使用 Matrix 视图
            return "要調整節點狀態，請使用 Matrix 視圖直接操作。\n\n或者告訴我具體要調整的節點名稱，我可以幫你生成 ChangeSet。"

        if any(keyword in message_lower for keyword in ['強調', '加強', 'emphasize']):
            return "要強調節點，請使用 Matrix 視圖直接操作。\n\n實驗調整會暫時套用到 Session，不會影響 Preset。"

        # 默认响应
        return f"實驗模式：你可以在 Matrix 視圖中調整節點狀態，然後在 Preview 中查看效果。\n\n當前 Session 有 {effective_lens.get('session_override_count', 0) if effective_lens else 0} 個實驗性調整。"

    def _handle_writeback(
        self,
        message: str,
        profile_id: str,
        workspace_id: Optional[str],
        session_id: Optional[str]
    ) -> str:
        """处理 Writeback 模式消息"""
        from ..changeset_service import ChangeSetService

        if not session_id:
            return "需要 Session ID 才能查看變更。"

        # 生成 ChangeSet
        resolver = self.resolver
        change_set_service = ChangeSetService(resolver, self.session_store)

        try:
            changeset = change_set_service.create_changeset(
                profile_id=profile_id,
                session_id=session_id,
                workspace_id=workspace_id
            )

            if changeset.changes:
                response = f"**變更摘要**：{changeset.summary}\n\n"
                response += f"共 {len(changeset.changes)} 個變更：\n"
                for change in changeset.changes[:5]:
                    response += f"- {change.node_label}: {change.from_state} → {change.to_state}\n"

                response += "\n你可以：\n"
                response += "- 套用到 Workspace（保存到工作區）\n"
                response += "- 更新 Preset（保存到全域預設）\n"
                response += "- 僅本次（不保存）"

                return response
            else:
                return "目前沒有待寫回的變更。"
        except Exception as e:
            logger.error(f"Failed to create changeset: {e}", exc_info=True)
            return f"無法生成變更摘要：{str(e)}"

