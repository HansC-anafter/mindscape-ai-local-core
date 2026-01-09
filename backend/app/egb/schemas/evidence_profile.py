"""
Intent Evidence Profile Schema

意圖證據剖面 - 同一 Intent 下的多次 Run 的證據彙總視圖。
這是 EGB 的核心輸出之一，用於回答「這張意圖卡的整體穩定度如何？」
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class DriftLevel(str, Enum):
    """漂移等級"""
    STABLE = "stable"        # 穩定（< 0.2）
    MILD = "mild"            # 輕微漂移（0.2 - 0.4）
    MODERATE = "moderate"    # 中度漂移（0.4 - 0.7）
    HIGH = "high"            # 高度漂移（> 0.7）

    @classmethod
    def from_score(cls, score: float) -> "DriftLevel":
        """根據分數返回漂移等級"""
        if score < 0.2:
            return cls.STABLE
        elif score < 0.4:
            return cls.MILD
        elif score < 0.7:
            return cls.MODERATE
        else:
            return cls.HIGH


@dataclass
class ToolPathSummary:
    """工具路徑摘要"""
    tool_sequence: List[str]  # 工具名序列，例如 ["search", "extract", "generate"]
    occurrence_count: int     # 出現次數
    success_rate: float       # 成功率 (0.0 - 1.0)
    avg_latency_ms: float     # 平均延遲

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_sequence": self.tool_sequence,
            "occurrence_count": self.occurrence_count,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }


@dataclass
class PolicyIntervention:
    """政策介入記錄"""
    intervention_id: str
    run_id: str
    intervention_type: str    # "blocked" | "upgraded_strictness" | "tool_denied" | "human_required"
    policy_name: str
    reason: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "run_id": self.run_id,
            "intervention_type": self.intervention_type,
            "policy_name": self.policy_name,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RunSummary:
    """單次執行摘要"""
    run_id: str
    trace_id: Optional[str]
    status: str               # "success" | "failed" | "cancelled"
    started_at: datetime
    ended_at: Optional[datetime]
    duration_ms: int
    tokens_used: int
    cost_usd: float
    tool_path: List[str]
    error_message: Optional[str] = None
    strictness_level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "tool_path": self.tool_path,
            "strictness_level": self.strictness_level,
        }
        if self.ended_at:
            result["ended_at"] = self.ended_at.isoformat()
        if self.error_message:
            result["error_message"] = self.error_message
        return result


@dataclass
class IntentEvidenceProfile:
    """
    意圖證據剖面

    同一 Intent 下的多次 Run 的證據彙總視圖。
    這是用戶在 IntentCard 上看到的「穩定度」和「歷史執行」的資料來源。

    用途：
    - 顯示意圖的整體穩定度
    - 顯示常見的執行路徑
    - 顯示政策介入的歷史
    - 幫助用戶理解「這個意圖的 AI 執行有多可靠」
    """

    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent_id: str = ""
    workspace_id: str = ""

    # 執行統計
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    # 時間範圍
    first_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None

    # 成本統計
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0

    # 穩定度指標
    stability_score: float = 1.0        # 0.0-1.0（穩定度指數）
    drift_level: DriftLevel = DriftLevel.STABLE

    # 證據摘要
    common_tool_paths: List[ToolPathSummary] = field(default_factory=list)
    common_retrieval_sources: List[str] = field(default_factory=list)
    policy_interventions: List[PolicyIntervention] = field(default_factory=list)

    # 關聯的 runs（最近 N 筆）
    run_summaries: List[RunSummary] = field(default_factory=list)

    # 元數據
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def success_rate(self) -> float:
        """計算成功率"""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs

    @property
    def avg_cost_per_run(self) -> float:
        """計算平均每次執行成本"""
        if self.total_runs == 0:
            return 0.0
        return self.total_cost_usd / self.total_runs

    @property
    def intervention_rate(self) -> float:
        """計算政策介入率"""
        if self.total_runs == 0:
            return 0.0
        return len(self.policy_interventions) / self.total_runs

    def update_stability_score(self) -> None:
        """
        更新穩定度分數

        穩定度考慮：
        - 成功率（越高越穩定）
        - 工具路徑一致性（越一致越穩定）
        - 政策介入率（越低越穩定）
        """
        # 成功率權重 40%
        success_factor = self.success_rate * 0.4

        # 路徑一致性權重 30%
        path_consistency = self._compute_path_consistency()
        path_factor = path_consistency * 0.3

        # 政策介入率（反向）權重 30%
        intervention_factor = (1 - min(self.intervention_rate, 1.0)) * 0.3

        self.stability_score = success_factor + path_factor + intervention_factor
        self.drift_level = DriftLevel.from_score(1 - self.stability_score)

    def _compute_path_consistency(self) -> float:
        """計算路徑一致性（最常見路徑的佔比）"""
        if not self.common_tool_paths or self.total_runs == 0:
            return 1.0

        # 最常見路徑的出現比例
        max_occurrence = max(p.occurrence_count for p in self.common_tool_paths)
        return max_occurrence / self.total_runs

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            "profile_id": self.profile_id,
            "intent_id": self.intent_id,
            "workspace_id": self.workspace_id,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "first_run_at": self.first_run_at.isoformat() if self.first_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "avg_latency_ms": self.avg_latency_ms,
            "stability_score": self.stability_score,
            "drift_level": self.drift_level.value,
            "success_rate": self.success_rate,
            "avg_cost_per_run": self.avg_cost_per_run,
            "intervention_rate": self.intervention_rate,
            "common_tool_paths": [p.to_dict() for p in self.common_tool_paths],
            "common_retrieval_sources": self.common_retrieval_sources,
            "policy_interventions": [i.to_dict() for i in self.policy_interventions],
            "run_summaries": [r.to_dict() for r in self.run_summaries],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentEvidenceProfile":
        """從字典反序列化"""
        profile = cls(
            profile_id=data.get("profile_id", str(uuid.uuid4())),
            intent_id=data["intent_id"],
            workspace_id=data["workspace_id"],
            total_runs=data.get("total_runs", 0),
            successful_runs=data.get("successful_runs", 0),
            failed_runs=data.get("failed_runs", 0),
            total_tokens=data.get("total_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            avg_latency_ms=data.get("avg_latency_ms", 0.0),
            stability_score=data.get("stability_score", 1.0),
            drift_level=DriftLevel(data.get("drift_level", "stable")),
            common_retrieval_sources=data.get("common_retrieval_sources", []),
        )

        # Parse datetime fields
        if data.get("first_run_at"):
            profile.first_run_at = datetime.fromisoformat(data["first_run_at"])
        if data.get("last_run_at"):
            profile.last_run_at = datetime.fromisoformat(data["last_run_at"])
        if data.get("created_at"):
            profile.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            profile.updated_at = datetime.fromisoformat(data["updated_at"])

        return profile

