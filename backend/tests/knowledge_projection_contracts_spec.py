from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from backend.app.services.knowledge_projection.retrievable.contracts import (
    ProjectionChannelReceipt,
)
from backend.app.services.knowledge_projection.retrievable.embedding_channels import (
    EmbeddingChannelRequest,
    KnowledgeEmbeddingChannelDescriptor,
    TextEmbeddingChannel,
)
from backend.app.services.knowledge_projection.retrievable.evidence_units import (
    EvidenceUnit,
    ImageRegionAnchor,
    TextSpanAnchor,
)


CONTENT_HASH = hashlib.sha256(b"evidence").hexdigest()


def test_typed_evidence_anchor_rejects_modality_mismatch():
    with pytest.raises(ValidationError, match="anchor_mismatch"):
        EvidenceUnit(
            evidence_unit_id="unit-1",
            unit_kind="image_region",
            source_ref="owner://asset/1",
            content_hash=CONTENT_HASH,
            anchor=TextSpanAnchor(start=0, end=8),
            retrievable_text="caption",
        )

    unit = EvidenceUnit(
        evidence_unit_id="unit-2",
        unit_kind="image_region",
        source_ref="owner://asset/2",
        content_hash=CONTENT_HASH,
        anchor=ImageRegionAnchor(x=0.1, y=0.2, width=0.4, height=0.3),
        retrievable_text="derived caption",
    )
    assert unit.anchor.kind == "image_region"


def test_pointer_is_not_reported_as_active_native_channel():
    with pytest.raises(ValidationError, match="active_receipt_incomplete"):
        ProjectionChannelReceipt(
            channel_id="image.colpali",
            modality="image",
            state="active",
            vector_count=1,
        )

    receipt = ProjectionChannelReceipt(
        channel_id="image.colpali",
        modality="image",
        state="unsupported",
        reason="native_image_channel_not_installed",
    )
    assert receipt.state == "unsupported"
    assert receipt.vector_count == 0


def test_text_channel_is_additive_and_dimension_checked():
    channel = TextEmbeddingChannel(
        descriptor=KnowledgeEmbeddingChannelDescriptor(
            channel_id="text.default",
            modality="text",
            model_revision="text-model-1",
            index_revision="text-index-1",
            dimension=3,
        ),
        embed_text=lambda text: (1.0, 2.0, float(len(text))),
    )
    results, receipt = channel.embed(
        [
            EmbeddingChannelRequest(
                evidence_unit_id="unit-1",
                modality="text",
                content_hash=CONTENT_HASH,
                retrievable_text="hello",
            )
        ]
    )

    assert len(results) == 1
    assert results[0].vectors == ((1.0, 2.0, 5.0),)
    assert receipt.state == "active"
    assert receipt.vector_count == 1
