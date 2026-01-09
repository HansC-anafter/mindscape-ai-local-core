"""
Decision Record Schema

決策紀錄 - 每次治理決策的完整記錄。
用於審計、學習和回溯。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class DecisionType(str, Enum):
    """決策類型"""
    PRESCRIPTION_APPLIED = "prescription_applied"    # 套用治理處方
    STRICTNESS_CHANGE = "strictness_change"          # 嚴謹度變更
    TOOLSET_CHANGE = "toolset_change"                # 工具集變更
    SCOPE_LOCK = "scope_lock"                        # 範圍鎖定
    MANUAL_OVERRIDE = "manual_override"              # 手動覆寫
    AUTO_ADJUSTMENT = "auto_adjustment"              # 自動調整


class DecisionSource(str, Enum):
    """決策來源"""
    EGB_PRESCRIPTION = "egb_prescription"            # EGB 治理處方
    USER_MANUAL = "user_manual"                      # 用戶手動
    POLICY_RULE = "policy_rule"                      # 政策規則
    SYSTEM_AUTO = "system_auto"                      # 系統自動


@dataclass
class EvidenceLink:
    """證據連結"""
    evidence_type: str           # "trace" | "span" | "drift_report" | "prescription"
    evidence_id: str
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_type": self.evidence_type,
            "evidence_id": self.evidence_id,
            "description": self.description,
        }


@dataclass
class DecisionRecord:
    """
    決策紀錄

    記錄每次治理決策的完整資訊，用於：
    - 審計追蹤（什麼時候、誰、做了什麼決策、基於什麼證據）
    - 學習改進（哪些決策帶來好結果）
    - 回溯分析（為什麼系統變成這樣）

    這是 GovernanceTuner 的輸出之一。
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 決策識別
    decision_type: DecisionType = DecisionType.PRESCRIPTION_APPLIED
    decision_source: DecisionSource = DecisionSource.EGB_PRESCRIPTION

    # 關聯 ID
    workspace_id: str = ""
    intent_id: str = ""
    run_id: str = ""
    prescription_id: Optional[str] = None

    # 決策內容
    decision_summary: str = ""           # 決策摘要（人話）
    changes_made: Dict[str, Any] = field(default_factory=dict)  # 具體變更

    # 決策原因
    rationale: str = ""                  # 為什麼做這個決策
    evidence_links: List[EvidenceLink] = field(default_factory=list)

    # 決策者
    decided_by: str = ""                 # user_id 或 "system"
    decided_at: datetime = field(default_factory=datetime.utcnow)

    # 政策資訊
    policy_version: Optional[str] = None
    policy_rules_triggered: List[str] = field(default_factory=list)

    # 狀態
    status: str = "executed"             # "executed" | "pending" | "reverted" | "failed"

    # 效果追蹤
    outcome_tracked: bool = False
    outcome_positive: Optional[bool] = None
    outcome_notes: Optional[str] = None

    # 元數據
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_user_decision(self) -> bool:
        """是否為用戶決策"""
        return self.decision_source == DecisionSource.USER_MANUAL

    @property
    def has_evidence(self) -> bool:
        """是否有證據支持"""
        return len(self.evidence_links) > 0

    def add_evidence(
        self,
        evidence_type: str,
        evidence_id: str,
        description: Optional[str] = None
    ) -> None:
        """添加證據連結"""
        self.evidence_links.append(EvidenceLink(
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            description=description,
        ))

    def mark_outcome(
        self,
        positive: bool,
        notes: Optional[str] = None
    ) -> None:
        """標記決策結果"""
        self.outcome_tracked = True
        self.outcome_positive = positive
        self.outcome_notes = notes

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            "record_id": self.record_id,
            "decision_type": self.decision_type.value,
            "decision_source": self.decision_source.value,
            "workspace_id": self.workspace_id,
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "prescription_id": self.prescription_id,
            "decision_summary": self.decision_summary,
            "changes_made": self.changes_made,
            "rationale": self.rationale,
            "evidence_links": [e.to_dict() for e in self.evidence_links],
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
            "policy_version": self.policy_version,
            "policy_rules_triggered": self.policy_rules_triggered,
            "status": self.status,
            "outcome_tracked": self.outcome_tracked,
            "outcome_positive": self.outcome_positive,
            "outcome_notes": self.outcome_notes,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionRecord":
        """從字典反序列化"""
        record = cls(
            record_id=data.get("record_id", str(uuid.uuid4())),
            decision_type=DecisionType(data.get("decision_type", "prescription_applied")),
            decision_source=DecisionSource(data.get("decision_source", "egb_prescription")),
            workspace_id=data.get("workspace_id", ""),
            intent_id=data.get("intent_id", ""),
            run_id=data.get("run_id", ""),
            prescription_id=data.get("prescription_id"),
            decision_summary=data.get("decision_summary", ""),
            changes_made=data.get("changes_made", {}),
            rationale=data.get("rationale", ""),
            decided_by=data.get("decided_by", ""),
            policy_version=data.get("policy_version"),
            policy_rules_triggered=data.get("policy_rules_triggered", []),
            status=data.get("status", "executed"),
            outcome_tracked=data.get("outcome_tracked", False),
            outcome_positive=data.get("outcome_positive"),
            outcome_notes=data.get("outcome_notes"),
            metadata=data.get("metadata", {}),
        )

        # Parse datetime fields
        if data.get("decided_at"):
            record.decided_at = datetime.fromisoformat(data["decided_at"])
        if data.get("created_at"):
            record.created_at = datetime.fromisoformat(data["created_at"])

        # Parse evidence links
        if data.get("evidence_links"):
            for link_data in data["evidence_links"]:
                record.evidence_links.append(EvidenceLink(
                    evidence_type=link_data["evidence_type"],
                    evidence_id=link_data["evidence_id"],
                    description=link_data.get("description"),
                ))

        return record

