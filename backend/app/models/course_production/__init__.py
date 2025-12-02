"""
Course Production Workflow Models

數據模型定義，用於線上課程錄製工作流 v0.2
通用設計，適用於各種類型的線上課程（瑜伽、健身、技能培訓等）
"""

from .voice_profile import (
    VoiceProfile,
    VoiceProfileStatus,
    CreateVoiceProfileRequest,
    UpdateVoiceProfileRequest,
    StartTrainingRequest,
)
from .voice_training_job import (
    VoiceTrainingJob,
    TrainingJobStatus,
    TrainingJobPriority,
)
from .video_segment import (
    VideoSegment,
    ShotType,
    SegmentQuality,
    CreateVideoSegmentRequest,
    UpdateVideoSegmentRequest,
    AnalyzeSegmentRequest,
    BatchAnalyzeRequest,
)

__all__ = [
    # Voice Profile
    "VoiceProfile",
    "VoiceProfileStatus",
    "CreateVoiceProfileRequest",
    "UpdateVoiceProfileRequest",
    "StartTrainingRequest",
    # Voice Training Job
    "VoiceTrainingJob",
    "TrainingJobStatus",
    "TrainingJobPriority",
    # Video Segment
    "VideoSegment",
    "ShotType",
    "SegmentQuality",
    "CreateVideoSegmentRequest",
    "UpdateVideoSegmentRequest",
    "AnalyzeSegmentRequest",
    "BatchAnalyzeRequest",
]
