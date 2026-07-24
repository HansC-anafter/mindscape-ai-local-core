"""Compatibility text projection over the structured Core Files parser."""

from __future__ import annotations

from typing import Any, Optional

from .document_parser_facade import parse_document


async def extract_text(
    file_path: str,
    file_type: Optional[str] = None,
    use_ocr: Optional[bool] = None,
) -> dict[str, Any]:
    """Preserve the legacy text result while using one parser truth."""
    envelope = await parse_document(
        file_path=file_path,
        file_type=file_type,
        allow_ocr=bool(use_ocr),
    )
    text = "\n\n".join(
        block.get("text", "").strip()
        for block in envelope.get("blocks", [])
        if block.get("text", "").strip()
    )
    confidences = [
        float(block["confidence"])
        for block in envelope.get("blocks", [])
        if block.get("confidence") is not None
    ]
    return {
        "text": text,
        "metadata": {
            "page_count": envelope["page_or_slide_count"],
            "word_count": len(text.split()),
            "file_path": file_path,
            "media_type": envelope["media_type"],
            "parser_version": envelope["parser_version"],
            "completeness": envelope["completeness"],
            "warnings": envelope["warnings"],
        },
        "ocr_used": envelope["ocr_used"],
        "quality": {
            "average_confidence": (
                sum(confidences) / len(confidences) if confidences else None
            ),
            "total_blocks": len(envelope.get("blocks", [])),
            "requires_ocr_pages": [
                page.get("page_or_slide") or page.get("logical_position")
                for page in envelope.get("pages", [])
                if page.get("requires_ocr")
            ],
        },
    }


__all__ = ["extract_text"]
