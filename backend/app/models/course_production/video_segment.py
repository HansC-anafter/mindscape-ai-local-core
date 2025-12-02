"""
Video Segment Model

視頻片段元數據定義
存儲在 Site-Hub (hub-db) - 素材索引表
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class ShotType(str, Enum):
    """鏡頭類型"""
    WIDE_FRONT = "wide_front"           # 全身正面
    WIDE_SIDE = "wide_side"             # 全身側面
    MEDIUM_FRONT = "medium_front"       # 半身正面
    MEDIUM_SIDE = "medium_side"         # 半身側面
    CLOSEUP = "closeup"                 # 特寫
    DETAIL = "detail"                   # 細節特寫（手、腳等）


class SegmentQuality(str, Enum):
    """片段品質等級"""
    EXCELLENT = "excellent"     # 優秀（可直接使用）
    GOOD = "good"               # 良好（可用）
    FAIR = "fair"               # 一般（需檢查）
    POOR = "poor"               # 較差（不推薦）


class VideoSegment(BaseModel):
    """
    視頻片段元數據
    
    存儲在 Site-Hub，實際視頻文件存儲在存儲服務中
    """
    id: str = Field(..., description="Segment ID (UUID)")
    instructor_id: str = Field(..., description="講師 ID")
    course_id: Optional[str] = Field(None, description="課程 ID（如果已關聯）")
    
    # 源文件信息
    source_video_path: str = Field(..., description="源視頻文件路徑")
    source_video_id: str = Field(..., description="源視頻 ID")
    
    # 時間範圍
    start_time: float = Field(..., ge=0.0, description="開始時間（秒）")
    end_time: float = Field(..., ge=0.0, description="結束時間（秒）")
    duration: float = Field(..., ge=0.0, description="時長（秒）")
    
    # 片段文件（如果已切分）
    segment_file_path: Optional[str] = Field(None, description="切分後的片段文件路徑")
    
    # 視覺特徵
    shot_type: Optional[ShotType] = Field(None, description="鏡頭類型")
    quality_score: float = Field(0.0, ge=0.0, le=1.0, description="品質分數")
    quality_level: SegmentQuality = Field(SegmentQuality.FAIR, description="品質等級")
    
    # 內容標籤
    tags: List[str] = Field(default_factory=list, description="標籤（如 '暖身', '主要動作序列'）")
    action_names: List[str] = Field(default_factory=list, description="動作名稱列表（課程特定術語）")
    intent_tags: List[str] = Field(default_factory=list, description="意圖標籤（如 '重點部位', '難度等級'）")
    
    # 腳本對齊
    script_line_ids: List[str] = Field(
        default_factory=list,
        description="對齊的腳本行 ID 列表（如 ['line_010', 'line_018']）"
    )
    script_alignment_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="對齊置信度"
    )
    
    # CV 分析結果（JSON）
    pose_estimation: Optional[Dict[str, Any]] = Field(None, description="姿態估計結果（如果適用）")
    composition_features: Optional[Dict[str, Any]] = Field(None, description="構圖特徵")
    lighting_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="光線品質")
    framing_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="構圖品質")
    
    # STT 結果
    transcript: Optional[str] = Field(None, description="語音轉錄文本")
    transcript_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="轉錄置信度")
    
    # 使用統計
    usage_count: int = Field(0, description="使用次數（被多少課程使用）")
    last_used_at: Optional[datetime] = Field(None, description="最後使用時間")
    
    # 元數據
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # 分析任務關聯
    analysis_job_id: Optional[str] = Field(None, description="分析任務 ID（如果由 SmartCut 生成）")
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CreateVideoSegmentRequest(BaseModel):
    """創建視頻片段請求"""
    instructor_id: str = Field(..., description="講師 ID")
    course_id: Optional[str] = Field(None, description="課程 ID")
    source_video_path: str = Field(..., description="源視頻文件路徑")
    source_video_id: str = Field(..., description="源視頻 ID")
    start_time: float = Field(..., ge=0.0, description="開始時間（秒）")
    end_time: float = Field(..., ge=0.0, description="結束時間（秒）")
    tags: Optional[List[str]] = Field(default_factory=list, description="標籤")


class UpdateVideoSegmentRequest(BaseModel):
    """更新視頻片段請求"""
    tags: Optional[List[str]] = Field(None, description="標籤")
    action_names: Optional[List[str]] = Field(None, description="動作名稱")
    intent_tags: Optional[List[str]] = Field(None, description="意圖標籤")
    shot_type: Optional[ShotType] = Field(None, description="鏡頭類型")
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="品質分數")
    quality_level: Optional[SegmentQuality] = Field(None, description="品質等級")


class AnalyzeSegmentRequest(BaseModel):
    """分析片段請求"""
    analyze_cv: bool = Field(True, description="是否進行 CV 分析")
    analyze_stt: bool = Field(True, description="是否進行 STT 分析")
    align_to_script: bool = Field(False, description="是否對齊到腳本")
    script_lines: Optional[List[Dict[str, Any]]] = Field(None, description="腳本行列表（如果對齊）")


class BatchAnalyzeRequest(BaseModel):
    """批量分析請求"""
    video_path: str = Field(..., description="視頻文件路徑")
    script_lines: Optional[List[Dict[str, Any]]] = Field(None, description="腳本行列表")
    instructor_id: str = Field(..., description="講師 ID")
    course_id: Optional[str] = Field(None, description="課程 ID")
