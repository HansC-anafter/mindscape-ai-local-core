import json
from typing import Any, Dict, Optional


def extract_source_text(embedding_record: Dict[str, Any]) -> Optional[str]:
    if "content" in embedding_record and embedding_record["content"]:
        return embedding_record["content"]

    metadata = embedding_record.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return None

    if isinstance(metadata, dict):
        for field in ["seed_text", "text", "content", "body"]:
            if field in metadata and metadata[field]:
                return metadata[field]

    return None
