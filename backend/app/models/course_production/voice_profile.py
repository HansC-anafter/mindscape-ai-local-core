"""
Voice Profile Model

聲紋模型元數據定義
存儲在 Site-Hub (hub-db) - 元數據表
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from ..workspace import Workspace  # 參考現有模型結構


class VoiceProfileStatus(str, Enum):
    """聲紋模型狀態"""
    PENDING = "pending"           # 等待訓練
    TRAINING = "training"         # 訓練中
    READY = "ready"               # 可用
    DEPRECATED = "deprecated"      # 已棄用
    FAILED = "failed"             # 訓練失敗


class VoiceProfile(BaseModel):
    """
    聲紋模型元數據
    
    存儲在 Site-Hub，實際模型文件存儲在 Semantic Hub 的存儲服務中
    """
    id: str = Field(..., description="Voice profile ID (UUID)")
    instructor_id: str = Field(..., description="講師 ID")

    # 版本管理
    version: int = Field(1, description="模型版本號")
    profile_name: str = Field(..., description="模型名稱（如 '我的 AI 聲音 v1'）")

    # 狀態
    status: VoiceProfileStatus = Field(VoiceProfileStatus.PENDING, description="模型狀態")

    # 訓練配置
    sample_duration_seconds: Optional[float] = Field(None, description="樣本總時長（秒）")
    sample_count: int = Field(0, description="樣本數量")
    sample_paths: List[str] = Field(default_factory=list, description="樣本文件路徑列表")

    # 模型存儲
    model_storage_path: Optional[str] = Field(None, description="模型文件存儲路徑（Semantic Hub）")
    model_storage_service: Optional[str] = Field(None, description="存儲服務標識（如 'semantic-hub-storage'）")

    # 訓練任務關聯
    training_job_id: Optional[str] = Field(None, description="關聯的訓練任務 ID")

    # 元數據
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = Field(None, description="模型就緒時間")

    # 品質指標（訓練完成後填充）
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="品質分數")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="相似度分數")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CreateVoiceProfileRequest(BaseModel):
    """創建聲紋模型請求"""
    instructor_id: str = Field(..., description="講師 ID")
    profile_name: str = Field(..., description="模型名稱")
    version: Optional[int] = Field(1, description="版本號（默認 1）")


class UpdateVoiceProfileRequest(BaseModel):
    """更新聲紋模型請求"""
    profile_name: Optional[str] = Field(None, description="模型名稱")
    status: Optional[VoiceProfileStatus] = Field(None, description="狀態")
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="品質分數")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="相似度分數")


class StartTrainingRequest(BaseModel):
    """啟動訓練請求"""
    training_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="訓練配置（模型類型、參數等）"
    )
    priority: Optional[str] = Field("normal", description="優先級：low/normal/high")
