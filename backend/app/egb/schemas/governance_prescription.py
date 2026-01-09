"""
Governance Prescription Schema

治理處方 - 「該調哪個旋鈕」的建議（可一鍵套用到 policy/strictness/toolset）。
這是 EGB 的核心輸出之一，用於回答「我該怎麼調整讓 AI 更穩定/更符合我的意圖？」
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid


class KnobType(str, Enum):
    """治理旋鈕類型"""
    STRICTNESS = "strictness"            # 嚴謹度 (0-3)
    TOOLSET = "toolset"                  # 工具集合（允許/禁止）
    SCOPE = "scope"                      # 資料範圍鎖定
    VERIFIER = "verifier"                # 驗證器開關
    CONSISTENCY_MODE = "consistency"     # 一致性模式
    COST_LIMIT = "cost_limit"            # 成本限制
    TEMPERATURE = "temperature"          # 溫度參數
    RETRIEVAL = "retrieval"              # 檢索策略


class ActionType(str, Enum):
    """治理動作類型"""
    INCREASE = "increase"                # 增加/升級
    DECREASE = "decrease"                # 減少/降級
    ENABLE = "enable"                    # 啟用
    DISABLE = "disable"                  # 停用
    SET = "set"                          # 設定為特定值
    LOCK = "lock"                        # 鎖定
    UNLOCK = "unlock"                    # 解鎖


@dataclass
class TunerRecommendation:
    """
    單一調參建議

    描述「該把哪個旋鈕從什麼值調到什麼值，以及為什麼」。
    """
    recommendation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 旋鈕資訊
    knob_type: KnobType = KnobType.STRICTNESS
    knob_name: str = ""                  # 人類可讀名稱

    # 當前與建議值
    current_value: Any = None
    suggested_value: Any = None

    # 原因與影響
    rationale: str = ""                  # 調整原因（人話）
    expected_impact: str = ""            # 預期影響

    # 優先級
    priority: str = "medium"             # "low" | "medium" | "high" | "critical"

    # 證據支持
    evidence_refs: List[str] = field(default_factory=list)  # span_id 引用

    # 風險
    risk_if_applied: str = "low"         # "low" | "medium" | "high"
    risk_if_ignored: str = "low"         # "low" | "medium" | "high"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "knob_type": self.knob_type.value,
            "knob_name": self.knob_name,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "rationale": self.rationale,
            "expected_impact": self.expected_impact,
            "priority": self.priority,
            "evidence_refs": self.evidence_refs,
            "risk_if_applied": self.risk_if_applied,
            "risk_if_ignored": self.risk_if_ignored,
        }


@dataclass
class GovernanceAction:
    """
    可執行的治理動作

    這是「一鍵套用」功能的資料結構。
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 動作資訊
    action_type: ActionType = ActionType.SET
    target_knob: KnobType = KnobType.STRICTNESS
    target_value: Any = None

    # 描述
    label: str = ""                      # 按鈕文字，例如「提高嚴謹度到 Level 2」
    description: str = ""

    # 是否需要確認
    requires_confirmation: bool = False
    confirmation_message: Optional[str] = None

    # 可逆性
    is_reversible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "target_knob": self.target_knob.value,
            "target_value": self.target_value,
            "label": self.label,
            "description": self.description,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_message": self.confirmation_message,
            "is_reversible": self.is_reversible,
        }


@dataclass
class ExpectedOutcome:
    """預期效果"""
    outcome_type: str                    # "stability" | "cost" | "latency" | "quality"
    direction: str                       # "improve" | "degrade" | "neutral"
    magnitude: str                       # "slight" | "moderate" | "significant"
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_type": self.outcome_type,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "description": self.description,
        }


@dataclass
class RiskAssessment:
    """風險評估"""
    overall_risk: str = "low"            # "low" | "medium" | "high"

    # 各面向風險
    stability_risk: str = "low"
    cost_risk: str = "low"
    quality_risk: str = "low"

    # 風險說明
    risk_factors: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_risk": self.overall_risk,
            "stability_risk": self.stability_risk,
            "cost_risk": self.cost_risk,
            "quality_risk": self.quality_risk,
            "risk_factors": self.risk_factors,
            "mitigations": self.mitigations,
        }


@dataclass
class GovernancePrescription:
    """
    治理處方

    包含多個調參建議和可執行動作。
    這是前端「治理旋鈕面板」的資料來源。

    用途：
    - 顯示「該調哪個旋鈕」
    - 提供「一鍵套用」功能
    - 預估調整後的效果
    """

    prescription_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent_id: str = ""
    run_id: str = ""
    workspace_id: str = ""

    # 建議的調整
    recommendations: List[TunerRecommendation] = field(default_factory=list)

    # 一鍵套用的 action
    applicable_actions: List[GovernanceAction] = field(default_factory=list)

    # 預期效果
    expected_outcomes: List[ExpectedOutcome] = field(default_factory=list)

    # 風險評估
    risk_assessment: Optional[RiskAssessment] = None

    # 生成方式
    generated_by: str = "rule_based"     # "rule_based" | "llm_assisted"
    confidence: float = 0.8              # 0.0-1.0

    # 狀態
    status: str = "pending"              # "pending" | "applied" | "rejected" | "expired"
    applied_at: Optional[datetime] = None
    applied_by: Optional[str] = None

    # 元數據
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    @property
    def has_critical_recommendations(self) -> bool:
        """是否有關鍵建議"""
        return any(r.priority == "critical" for r in self.recommendations)

    @property
    def primary_recommendation(self) -> Optional[TunerRecommendation]:
        """獲取最重要的建議"""
        if not self.recommendations:
            return None
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_recs = sorted(
            self.recommendations,
            key=lambda r: priority_order.get(r.priority, 4)
        )
        return sorted_recs[0]

    @property
    def quick_actions(self) -> List[GovernanceAction]:
        """獲取可快速執行的動作（不需要確認）"""
        return [a for a in self.applicable_actions if not a.requires_confirmation]

    def get_recommendations_by_knob(self, knob_type: KnobType) -> List[TunerRecommendation]:
        """按旋鈕類型獲取建議"""
        return [r for r in self.recommendations if r.knob_type == knob_type]

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            "prescription_id": self.prescription_id,
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "applicable_actions": [a.to_dict() for a in self.applicable_actions],
            "expected_outcomes": [o.to_dict() for o in self.expected_outcomes],
            "risk_assessment": self.risk_assessment.to_dict() if self.risk_assessment else None,
            "generated_by": self.generated_by,
            "confidence": self.confidence,
            "status": self.status,
            "has_critical_recommendations": self.has_critical_recommendations,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "applied_by": self.applied_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GovernancePrescription":
        """從字典反序列化"""
        prescription = cls(
            prescription_id=data.get("prescription_id", str(uuid.uuid4())),
            intent_id=data["intent_id"],
            run_id=data["run_id"],
            workspace_id=data.get("workspace_id", ""),
            generated_by=data.get("generated_by", "rule_based"),
            confidence=data.get("confidence", 0.8),
            status=data.get("status", "pending"),
            applied_by=data.get("applied_by"),
        )

        # Parse datetime fields
        if data.get("created_at"):
            prescription.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("expires_at"):
            prescription.expires_at = datetime.fromisoformat(data["expires_at"])
        if data.get("applied_at"):
            prescription.applied_at = datetime.fromisoformat(data["applied_at"])

        return prescription

