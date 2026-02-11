"""
Correlation IDs Schema

關聯 ID 體系 - 貫穿整條治理鏈路的標識符系統。
用於連接 Intent Layer 與 Trace Layer。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import uuid
import hashlib


@dataclass
class CorrelationIds:
    """
    EGB 關聯 ID 體系

    這些 ID 會被傳播到 Langfuse 的 trace/span metadata 中，
    使得治理層可以反查觀測證據，觀測層可以關聯治理決策。

    ⚠️ 關鍵設計決策：trace_id = run_id（單一真相）

    Mapping to Langfuse:
        workspace_id  → metadata.workspace_id
        intent_id     → tags: ["intent:xxx"], session_id
        decision_id   → metadata.decision_id
        playbook_id   → metadata.playbook_id
        run_id        → trace.id（這是唯一的執行識別符）
        session_id    → Langfuse session_id (同一 intent 的多次 run)

    注意：不再有獨立的 trace_id，run_id 就是 trace_id。
    這確保了查詢、快取、回放的一致性。
    """

    # 治理層 ID（Mindscape 控制）
    workspace_id: str
    intent_id: str
    decision_id: str
    playbook_id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 觀測層 ID
    # 注意：trace_id 已移除，統一使用 run_id 作為 Langfuse trace.id
    session_id: Optional[str] = None

    # Mind-Lens 影響
    mind_lens_level: int = 0  # 心智鏡影響深度 (0-3)
    strictness_level: int = 0  # 嚴謹度等級 (0-3)

    # 版本控制
    policy_version: Optional[str] = None
    playbook_version: Optional[str] = None
    model_version: Optional[str] = None

    # 時間戳
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def trace_id(self) -> str:
        """
        trace_id 就是 run_id（單一真相）

        這是一個只讀屬性，確保向後相容性。
        """
        return self.run_id

    def to_langfuse_metadata(self) -> Dict[str, Any]:
        """轉換為 Langfuse metadata 格式"""
        return {
            "workspace_id": self.workspace_id,
            "intent_id": self.intent_id,
            "decision_id": self.decision_id,
            "playbook_id": self.playbook_id,
            "run_id": self.run_id,
            # trace_id 不再單獨存，因為 trace_id = run_id
            "mind_lens_level": self.mind_lens_level,
            "strictness_level": self.strictness_level,
            "policy_version": self.policy_version,
            "playbook_version": self.playbook_version,
            "model_version": self.model_version,
        }

    def to_langfuse_tags(self) -> list:
        """轉換為 Langfuse tags 格式"""
        tags = [
            f"intent:{self.intent_id}",
            f"strictness:{self.strictness_level}",
            f"lens:{self.mind_lens_level}",
        ]
        if self.playbook_id:
            tags.append(f"playbook:{self.playbook_id}")
        return tags

    def get_session_id(self) -> str:
        """
        獲取 Langfuse session_id
        同一張 Intent Card 的多次 run 共享同一個 session
        """
        if self.session_id:
            return self.session_id
        return f"intent:{self.intent_id}"

    def get_cache_context_hash(self) -> str:
        """
        生成治理上下文 hash，用於 cache key

        ⚠️ P0-4 硬規則：cache key 必須包含治理上下文 hash
        格式：sha1(policy_version + strictness + lens_level + playbook_id)

        ⚠️ 設計決策：
        - 包含：policy_version, strictness_level, mind_lens_level, playbook_id
        - 不包含：playbook_version, model_version
        - 理由：playbook 只影響工具路徑（已由 path_drift 計算），model 只影響 cost（已由 cost_drift 計算）

        Returns:
            str: 上下文 hash（16 字元）
        """
        # 構建上下文字串
        ctx_parts = [
            self.policy_version or "default",
            str(self.strictness_level),
            str(self.mind_lens_level),
            self.playbook_id or "default",
        ]
        ctx_str = ":".join(ctx_parts)

        # 計算 hash
        ctx_hash = hashlib.sha1(ctx_str.encode()).hexdigest()[:16]
        return ctx_hash

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            "workspace_id": self.workspace_id,
            "intent_id": self.intent_id,
            "decision_id": self.decision_id,
            "playbook_id": self.playbook_id,
            "run_id": self.run_id,
            # trace_id 由 run_id 衍生，不單獨存儲
            "session_id": self.session_id,
            "mind_lens_level": self.mind_lens_level,
            "strictness_level": self.strictness_level,
            "policy_version": self.policy_version,
            "playbook_version": self.playbook_version,
            "model_version": self.model_version,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrelationIds":
        """從字典反序列化"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()

        # 向後相容：如果有 trace_id 但沒有 run_id，使用 trace_id
        run_id = data.get("run_id") or data.get("trace_id") or str(uuid.uuid4())

        return cls(
            workspace_id=data["workspace_id"],
            intent_id=data["intent_id"],
            decision_id=data["decision_id"],
            playbook_id=data["playbook_id"],
            run_id=run_id,
            session_id=data.get("session_id"),
            mind_lens_level=data.get("mind_lens_level", 0),
            strictness_level=data.get("strictness_level", 0),
            policy_version=data.get("policy_version"),
            playbook_version=data.get("playbook_version"),
            model_version=data.get("model_version"),
            created_at=created_at,
        )

