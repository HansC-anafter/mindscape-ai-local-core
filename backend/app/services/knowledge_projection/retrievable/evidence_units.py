"""Portable cross-modality evidence units with typed, bounded anchors."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextSpanAnchor(_StrictModel):
    kind: Literal["text_span"] = "text_span"
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "TextSpanAnchor":
        if self.end <= self.start:
            raise ValueError("knowledge_evidence_text_span_invalid")
        return self


class ImageRegionAnchor(_StrictModel):
    kind: Literal["image_region"] = "image_region"
    page: Optional[int] = Field(default=None, ge=0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ImageRegionAnchor":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("knowledge_evidence_image_region_out_of_bounds")
        return self


class VideoTimeRangeAnchor(_StrictModel):
    kind: Literal["video_time_range"] = "video_time_range"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    keyframe_ref: Optional[str] = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_range(self) -> "VideoTimeRangeAnchor":
        if self.end_ms <= self.start_ms:
            raise ValueError("knowledge_evidence_video_range_invalid")
        return self


class AudioTimeRangeAnchor(_StrictModel):
    kind: Literal["audio_time_range"] = "audio_time_range"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "AudioTimeRangeAnchor":
        if self.end_ms <= self.start_ms:
            raise ValueError("knowledge_evidence_audio_range_invalid")
        return self


EvidenceAnchor = Annotated[
    Union[
        TextSpanAnchor,
        ImageRegionAnchor,
        VideoTimeRangeAnchor,
        AudioTimeRangeAnchor,
    ],
    Field(discriminator="kind"),
]


class DerivativeRef(_StrictModel):
    kind: Literal[
        "caption",
        "transcript",
        "ocr_text",
        "vision_summary",
        "keyframe",
        "waveform",
    ]
    ref: str = Field(min_length=1, max_length=1024)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceUnit(_StrictModel):
    """One logical evidence unit; physical embedding channels remain additive."""

    evidence_unit_id: str = Field(min_length=1, max_length=255)
    unit_kind: Literal["text_span", "image_region", "video_segment", "audio_segment"]
    source_ref: str = Field(min_length=1, max_length=1024)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    anchor: EvidenceAnchor
    retrievable_text: Optional[str] = Field(default=None, max_length=32768)
    derivatives: tuple[DerivativeRef, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_kind_anchor(self) -> "EvidenceUnit":
        expected = {
            "text_span": "text_span",
            "image_region": "image_region",
            "video_segment": "video_time_range",
            "audio_segment": "audio_time_range",
        }[self.unit_kind]
        if self.anchor.kind != expected:
            raise ValueError("knowledge_evidence_unit_anchor_mismatch")
        if self.unit_kind == "text_span" and not (self.retrievable_text or "").strip():
            raise ValueError("knowledge_evidence_text_required")
        return self
