"""
Voice Training Job Model

Voice training job definition
Stored in external database - job tracking table
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class TrainingJobStatus(str, Enum):
    """訓練任務狀態"""
    QUEUED = "queued"             # 排隊中
    PREPARING = "preparing"       # 準備樣本
    TRAINING = "training"         # 訓練中
    VALIDATING = "validating"     # 驗證中
    COMPLETED = "completed"       # 完成
    FAILED = "failed"             # 失敗
    CANCELLED = "cancelled"       # 已取消


class TrainingJobPriority(str, Enum):
    """任務優先級"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class VoiceTrainingJob(BaseModel):
    """
    Voice training job

    Stored in external database, responsible for actual training execution
    """
    id: str = Field(..., description="Training job ID (UUID)")
    voice_profile_id: str = Field(..., description="關聯的 voice profile ID")
    instructor_id: str = Field(..., description="講師 ID")

    # 任務狀態
    status: TrainingJobStatus = Field(TrainingJobStatus.QUEUED, description="任務狀態")
    priority: TrainingJobPriority = Field(TrainingJobPriority.NORMAL, description="優先級")

    # 訓練配置
    training_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="訓練配置（模型類型、參數等）"
    )

    # 樣本信息
    sample_file_paths: List[str] = Field(default_factory=list, description="樣本文件路徑")
    sample_metadata: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="樣本元數據（時長、品質等）"
    )

    # 執行信息
    started_at: Optional[datetime] = Field(None, description="開始時間")
    completed_at: Optional[datetime] = Field(None, description="完成時間")
    estimated_duration_seconds: Optional[int] = Field(None, description="預估時長（秒）")
    actual_duration_seconds: Optional[int] = Field(None, description="實際時長（秒）")

    # 結果
    result_model_path: Optional[str] = Field(None, description="生成的模型文件路徑")
    result_metrics: Optional[Dict[str, Any]] = Field(None, description="訓練指標")
    error_message: Optional[str] = Field(None, description="錯誤信息（如果失敗）")
    error_stack: Optional[str] = Field(None, description="錯誤堆棧")

    # 資源使用
    gpu_used: Optional[str] = Field(None, description="使用的 GPU 資源")
    compute_cost: Optional[float] = Field(None, description="計算成本（如果可追蹤）")

    # 元數據
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 日誌
    log_path: Optional[str] = Field(None, description="訓練日誌文件路徑")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
