"""Additive embedding channel ports; only text is implemented in the MVP."""

from __future__ import annotations

from typing import Callable, Literal, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .contracts import ProjectionChannelReceipt


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        protected_namespaces=(),
    )


class KnowledgeEmbeddingChannelDescriptor(_StrictModel):
    channel_id: str = Field(pattern=r"^[a-z0-9_.-]+$")
    modality: Literal["text", "image", "video", "audio"]
    model_revision: str = Field(min_length=1, max_length=255)
    index_revision: str = Field(min_length=1, max_length=255)
    dimension: int = Field(ge=1, le=65536)


class EmbeddingChannelRequest(_StrictModel):
    evidence_unit_id: str = Field(min_length=1, max_length=255)
    modality: Literal["text", "image", "video", "audio"]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    retrievable_text: Optional[str] = Field(default=None, max_length=32768)
    owner_pointer: Optional[str] = Field(default=None, max_length=1024)


class EmbeddingChannelResult(_StrictModel):
    evidence_unit_id: str
    vectors: tuple[tuple[float, ...], ...] = Field(min_length=1, max_length=1024)


class KnowledgeEmbeddingChannel(Protocol):
    descriptor: KnowledgeEmbeddingChannelDescriptor

    def embed(
        self,
        requests: Sequence[EmbeddingChannelRequest],
    ) -> tuple[tuple[EmbeddingChannelResult, ...], ProjectionChannelReceipt]: ...


class TextEmbeddingChannel:
    """Bounded text channel adapter around an injected embedding primitive."""

    def __init__(
        self,
        *,
        descriptor: KnowledgeEmbeddingChannelDescriptor,
        embed_text: Callable[[str], Sequence[float]],
    ) -> None:
        if descriptor.modality != "text":
            raise ValueError("knowledge_text_channel_modality_required")
        self.descriptor = descriptor
        self._embed_text = embed_text

    def embed(
        self,
        requests: Sequence[EmbeddingChannelRequest],
    ) -> tuple[tuple[EmbeddingChannelResult, ...], ProjectionChannelReceipt]:
        if len(requests) > 2000:
            raise ValueError("knowledge_text_channel_request_budget_exceeded")
        results: list[EmbeddingChannelResult] = []
        for request in requests:
            if request.modality != "text" or not (request.retrievable_text or "").strip():
                raise ValueError("knowledge_text_channel_input_required")
            vector = tuple(float(item) for item in self._embed_text(request.retrievable_text))
            if len(vector) != self.descriptor.dimension:
                raise ValueError("knowledge_text_channel_dimension_mismatch")
            results.append(
                EmbeddingChannelResult(
                    evidence_unit_id=request.evidence_unit_id,
                    vectors=(vector,),
                )
            )
        receipt = ProjectionChannelReceipt(
            channel_id=self.descriptor.channel_id,
            modality="text",
            state="active" if results else "not_admitted",
            model_revision=self.descriptor.model_revision if results else None,
            index_revision=self.descriptor.index_revision if results else None,
            vector_count=len(results),
            reason=None if results else "no_text_evidence_admitted",
        )
        return tuple(results), receipt
