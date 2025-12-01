"""
Habit Learning Models
定義習慣觀察、候選習慣和審計記錄的資料模型
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class HabitCategory(str, Enum):
    """習慣分類"""
    PREFERENCE = "preference"  # 偏好設定（語言、語氣等）
    TOOL_USAGE = "tool_usage"  # 工具使用習慣
    TIME_PATTERN = "time_pattern"  # 時間模式
    PLAYBOOK_USAGE = "playbook_usage"  # Playbook 使用習慣


class HabitCandidateStatus(str, Enum):
    """候選習慣狀態"""
    PENDING = "pending"  # 待確認
    CONFIRMED = "confirmed"  # 已確認
    REJECTED = "rejected"  # 已拒絕
    SUPERSEDED = "superseded"  # 已被取代


class HabitAuditAction(str, Enum):
    """審計操作類型"""
    CREATED = "created"  # 建立
    CONFIRMED = "confirmed"  # 確認
    REJECTED = "rejected"  # 拒絕
    SUPERSEDED = "superseded"  # 取代
    ROLLED_BACK = "rolled_back"  # 回滾


class HabitObservation(BaseModel):
    """習慣觀察記錄"""
    id: str = Field(..., description="唯一識別符")
    profile_id: str = Field(..., description="關聯的 profile ID")

    # 觀察內容
    habit_key: str = Field(..., description="習慣鍵值（如 'language', 'communication_style'）")
    habit_value: str = Field(..., description="觀察到的值（如 'zh-TW', 'casual'）")
    habit_category: HabitCategory = Field(..., description="習慣分類")

    # 來源資訊
    source_type: str = Field(..., description="來源類型（'agent_execution', 'playbook_execution', 'webhook', 'chat'）")
    source_id: Optional[str] = Field(None, description="來源記錄 ID（如 execution_id）")
    source_context: Optional[Dict[str, Any]] = Field(None, description="額外上下文（JSON 格式）")

    # Insight 訊號（用於彈性創意採集）
    has_insight_signal: bool = Field(default=False, description="是否包含創意/洞見訊號")
    insight_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Insight 分數（0-1）")

    # 時間戳記
    observed_at: datetime = Field(default_factory=datetime.utcnow, description="觀察時間")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="建立時間")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HabitCandidate(BaseModel):
    """候選習慣"""
    id: str = Field(..., description="唯一識別符")
    profile_id: str = Field(..., description="關聯的 profile ID")

    # 候選習慣
    habit_key: str = Field(..., description="習慣鍵值")
    habit_value: str = Field(..., description="習慣值")
    habit_category: HabitCategory = Field(..., description="習慣分類")

    # 統計資訊
    evidence_count: int = Field(default=0, description="觀察次數")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="信心度（0.0-1.0）")
    first_seen_at: Optional[datetime] = Field(None, description="首次觀察時間")
    last_seen_at: Optional[datetime] = Field(None, description="最後觀察時間")

    # 證據引用
    evidence_refs: List[str] = Field(default_factory=list, description="觀察記錄 ID 列表")

    # 狀態
    status: HabitCandidateStatus = Field(default=HabitCandidateStatus.PENDING, description="狀態")

    # 時間戳記
    created_at: datetime = Field(default_factory=datetime.utcnow, description="建立時間")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新時間")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HabitAuditLog(BaseModel):
    """習慣審計記錄"""
    id: str = Field(..., description="唯一識別符")
    profile_id: str = Field(..., description="關聯的 profile ID")
    candidate_id: str = Field(..., description="關聯的 candidate ID")

    # 變更資訊
    action: HabitAuditAction = Field(..., description="操作類型")
    previous_status: Optional[HabitCandidateStatus] = Field(None, description="變更前的狀態")
    new_status: Optional[HabitCandidateStatus] = Field(None, description="變更後的狀態")

    # 操作者資訊
    actor_type: str = Field(default="system", description="操作者類型（'system', 'user'）")
    actor_id: Optional[str] = Field(None, description="操作者 ID")

    # 原因/備註
    reason: Optional[str] = Field(None, description="變更原因")
    metadata: Optional[Dict[str, Any]] = Field(None, description="額外資訊（JSON 格式）")

    # 時間戳記
    created_at: datetime = Field(default_factory=datetime.utcnow, description="建立時間")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# API Request/Response models

class CreateHabitObservationRequest(BaseModel):
    """建立習慣觀察的請求"""
    habit_key: str
    habit_value: str
    habit_category: HabitCategory
    source_type: str
    source_id: Optional[str] = None
    source_context: Optional[Dict[str, Any]] = None


class ConfirmHabitCandidateRequest(BaseModel):
    """確認候選習慣的請求"""
    reason: Optional[str] = None


class RejectHabitCandidateRequest(BaseModel):
    """拒絕候選習慣的請求"""
    reason: Optional[str] = None


class HabitCandidateResponse(BaseModel):
    """候選習慣回應"""
    candidate: HabitCandidate
    suggestion_message: str = Field(..., description="建議訊息（用於 UI 顯示）")


class HabitMetricsResponse(BaseModel):
    """習慣學習統計資訊"""
    total_observations: int
    total_candidates: int
    pending_candidates: int
    confirmed_candidates: int
    rejected_candidates: int
    acceptance_rate: float = Field(ge=0.0, le=1.0, description="接受率（confirmed / (confirmed + rejected)）")
    candidate_hit_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="候選命中率（產生候選的觀察記錄比例）"
    )
    is_habit_suggestions_enabled: Optional[bool] = Field(
        None,
        description="習慣建議功能是否啟用"
    )
