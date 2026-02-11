"""
Document processing utilities for local-core.

Provides generic document processing capabilities:
- Document length checking
- Token estimation
- Language detection
- Document chunking (paragraphs, sentences)

These are generic utilities that can be used by any capability.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

# Model context limits (in tokens)
MODEL_CONTEXT_LIMITS = {
    "claude-3-5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
}

# Token estimation ratios (characters per token)
TOKEN_RATIOS = {
    "zh": 1.3,  # Chinese: ~1.3 characters per token
    "en": 4.0,  # English: ~4 characters per token
    "mixed": 2.5,  # Mixed: ~2.5 characters per token
}


class DocumentChunk:
    """Represents a chunk of a document."""

    def __init__(self, content: str, start_index: int, end_index: int, chunk_index: int):
        self.content = content
        self.start_index = start_index
        self.end_index = end_index
        self.chunk_index = chunk_index

    def __len__(self):
        return len(self.content)


def get_model_context_limit(model: str) -> int:
    """
    Get the context limit for a given model (in tokens).

    Args:
        model: Model name (e.g., "claude-3-5-sonnet")

    Returns:
        Context limit in tokens, or default 200000 if model not found
    """
    model_lower = model.lower()

    if model_lower in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model_lower]

    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key in model_lower or model_lower in key:
            return limit

    logger.warning(f"Unknown model {model}, using default context limit 200000")
    return 200000


def estimate_tokens(content: str, language: str = "zh") -> int:
    """
    Estimate the number of tokens in content.

    Args:
        content: Text content
        language: Language code ("zh", "en", "mixed")

    Returns:
        Estimated token count
    """
    ratio = TOKEN_RATIOS.get(language, TOKEN_RATIOS["mixed"])
    return int(len(content) / ratio)


def detect_language(content: str) -> str:
    """
    Detect the primary language of content.

    Simple heuristic: count Chinese characters vs English characters.

    Args:
        content: Text content

    Returns:
        Language code ("zh", "en", "mixed")
    """
    chinese_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
    total_chars = len([c for c in content if c.isalnum() or '\u4e00' <= c <= '\u9fff'])

    if total_chars == 0:
        return "mixed"

    chinese_ratio = chinese_chars / total_chars

    if chinese_ratio > 0.7:
        return "zh"
    elif chinese_ratio < 0.3:
        return "en"
    else:
        return "mixed"


def check_document_length(
    content: str,
    model: str = "claude-3-5-sonnet",
    buffer_ratio: float = 0.2
) -> Dict[str, Any]:
    """
    Check if document length exceeds context limit.

    Args:
        content: Document content
        model: LLM model name
        buffer_ratio: Buffer ratio for prompt and output (default 0.2 = 20%)

    Returns:
        {
            "within_limit": bool,
            "content_length": int,
            "estimated_tokens": int,
            "max_tokens": int,
            "available_tokens": int,
            "needs_chunking": bool,
            "language": str
        }
    """
    language = detect_language(content)
    estimated_tokens = estimate_tokens(content, language)
    max_tokens = get_model_context_limit(model)

    available_tokens = int(max_tokens * (1 - buffer_ratio))

    within_limit = estimated_tokens <= available_tokens
    needs_chunking = not within_limit

    return {
        "within_limit": within_limit,
        "content_length": len(content),
        "estimated_tokens": estimated_tokens,
        "max_tokens": max_tokens,
        "available_tokens": available_tokens,
        "needs_chunking": needs_chunking,
        "language": language
    }


def chunk_document_by_paragraphs(content: str, max_chunk_size: int = 100000) -> List[str]:
    """
    Chunk document by paragraphs.

    Args:
        content: Document content
        max_chunk_size: Maximum chunk size in characters

    Returns:
        List of chunk strings
    """
    paragraphs = content.split('\n\n')

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)

        if para_size > max_chunk_size:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

            sentences = para.split('。') if '。' in para else para.split('.')
            for sent in sentences:
                sent_size = len(sent)
                if current_size + sent_size > max_chunk_size:
                    if current_chunk:
                        chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [sent]
                    current_size = sent_size
                else:
                    current_chunk.append(sent)
                    current_size += sent_size
        elif current_size + para_size > max_chunk_size:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def chunk_document_by_sentences(content: str, max_chunk_size: int = 100000) -> List[str]:
    """
    Chunk document by sentences (fallback when paragraphs are too long).

    Args:
        content: Document content
        max_chunk_size: Maximum chunk size in characters

    Returns:
        List of chunk strings
    """
    if '。' in content:
        sentences = content.split('。')
        delimiter = '。'
    elif '.' in content:
        sentences = content.split('.')
        delimiter = '.'
    else:
        return [content]

    chunks = []
    current_chunk = []
    current_size = 0

    for sent in sentences:
        sent_with_delimiter = sent + delimiter if sent != sentences[-1] else sent
        sent_size = len(sent_with_delimiter)

        if sent_size > max_chunk_size:
            if current_chunk:
                chunks.append(''.join(current_chunk))
            chunks.append(sent_with_delimiter)
            current_chunk = []
            current_size = 0
        elif current_size + sent_size > max_chunk_size:
            if current_chunk:
                chunks.append(''.join(current_chunk))
            current_chunk = [sent_with_delimiter]
            current_size = sent_size
        else:
            current_chunk.append(sent_with_delimiter)
            current_size += sent_size

    if current_chunk:
        chunks.append(''.join(current_chunk))

    return chunks


def chunk_document_to_objects(
    content: str,
    max_chunk_size: int = 100000,
    strategy: str = "paragraph"
) -> List[DocumentChunk]:
    """
    Chunk document and return DocumentChunk objects.

    Args:
        content: Document content
        max_chunk_size: Maximum chunk size in characters
        strategy: Chunking strategy ("paragraph" or "sentence")

    Returns:
        List of DocumentChunk objects
    """
    if strategy == "sentence":
        chunk_strings = chunk_document_by_sentences(content, max_chunk_size)
    else:
        chunk_strings = chunk_document_by_paragraphs(content, max_chunk_size)

    document_chunks = []
    current_index = 0

    for i, chunk_content in enumerate(chunk_strings):
        start_index = current_index
        end_index = current_index + len(chunk_content)

        chunk = DocumentChunk(
            content=chunk_content,
            start_index=start_index,
            end_index=end_index,
            chunk_index=i
        )
        document_chunks.append(chunk)

        current_index = end_index

    return document_chunks


def extract_changed_sections(
    old_content: str,
    new_content: str,
    context_lines: int = 3
) -> List[Dict[str, Any]]:
    """
    Extract changed sections from document using diff analysis.

    This is a generic utility that can be used by any capability.

    Args:
        old_content: Previous document content
        new_content: Updated document content
        context_lines: Number of context lines to include around changes

    Returns:
        List of changed sections with metadata:
        {
            "type": str,  # 'replace' or 'insert'
            "old_start": int,
            "old_end": int,
            "new_start": int,
            "new_end": int,
            "content": str,
            "line_start": int,
            "line_end": int
        }
    """
    import difflib

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    differ = difflib.SequenceMatcher(None, old_lines, new_lines)
    changed_sections = []

    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == 'replace' or tag == 'insert':
            start_line = max(0, j1 - context_lines)
            end_line = min(len(new_lines), j2 + context_lines)

            changed_content = ''.join(new_lines[start_line:end_line])
            changed_sections.append({
                "type": tag,
                "old_start": i1,
                "old_end": i2,
                "new_start": j1,
                "new_end": j2,
                "content": changed_content,
                "line_start": start_line,
                "line_end": end_line
            })

    return changed_sections


def calculate_content_hash(content: str) -> str:
    """
    Calculate hash of document content for version tracking.

    Args:
        content: Document content

    Returns:
        SHA256 hash string
    """
    import hashlib
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def detect_document_changes(
    old_content: str,
    new_content: str
) -> Dict[str, Any]:
    """
    Detect changes between two document versions.

    Args:
        old_content: Previous version content
        new_content: New version content

    Returns:
        Change detection result:
        {
            "changed": bool,
            "old_hash": str,
            "new_hash": str,
            "old_length": int,
            "new_length": int,
            "length_diff": int,
            "similarity": float,
            "change_type": str
        }
    """
    import difflib

    old_hash = calculate_content_hash(old_content)
    new_hash = calculate_content_hash(new_content)

    if old_hash == new_hash:
        return {
            "changed": False,
            "old_hash": old_hash,
            "new_hash": new_hash,
            "change_type": "no_change"
        }

    old_length = len(old_content)
    new_length = len(new_content)
    length_diff = new_length - old_length

    similarity = difflib.SequenceMatcher(None, old_content, new_content).ratio()

    return {
        "changed": True,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "old_length": old_length,
        "new_length": new_length,
        "length_diff": length_diff,
        "similarity": similarity,
        "change_type": "modified" if similarity > 0.5 else "major_change"
    }


def track_document_version(
    document_id: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    persist: bool = True,
    storage_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Track document version.

    This is a generic utility. For brand-specific version tracking,
    use brand_identity capability's version tracking.

    Args:
        document_id: Document identifier
        content: Document content
        metadata: Optional metadata
        persist: Whether to persist to storage (default: True)
        storage_dir: Storage directory (default: /tmp/document_versions or env var)

    Returns:
        Version tracking info
    """
    import os
    import json
    from pathlib import Path

    content_hash = calculate_content_hash(content)
    version_info = {
        "document_id": document_id,
        "content_hash": content_hash,
        "content_length": len(content),
        "version_timestamp": _utc_now().isoformat(),
        "metadata": metadata or {}
    }

    if persist:
        storage_path = storage_dir or os.getenv("DOCUMENT_VERSION_STORAGE", "/tmp/document_versions")
        storage_dir_path = Path(storage_path)
        storage_dir_path.mkdir(parents=True, exist_ok=True)

        # Sanitize document_id for filesystem
        safe_document_id = _sanitize_document_id(document_id)
        history_file = storage_dir_path / f"{safe_document_id}.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = {"document_id": document_id, "versions": []}

            history["versions"].append(version_info)
            history["last_updated"] = _utc_now().isoformat()

            if len(history["versions"]) > 50:
                history["versions"] = history["versions"][-50:]

            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved version for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to save version for {document_id}: {e}", exc_info=True)

    logger.info(f"Tracked version for document {document_id}: hash={content_hash[:8]}...")
    return version_info


def _sanitize_document_id(document_id: str) -> str:
    """
    Sanitize document_id for use as filename.

    Args:
        document_id: Original document identifier (may contain /, :, etc.)

    Returns:
        Sanitized identifier safe for filesystem
    """
    import hashlib
    import re

    if '/' in document_id or '\\' in document_id or ':' in document_id:
        safe_hash = hashlib.sha256(document_id.encode('utf-8')).hexdigest()[:16]
        safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', document_id[:20])
        return f"{safe_prefix}_{safe_hash}"
    else:
        return re.sub(r'[^a-zA-Z0-9._-]', '_', document_id)


def get_document_version_history(
    document_id: str,
    storage_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get document version history.

    Args:
        document_id: Document identifier (may contain path separators)
        storage_dir: Storage directory (default: /tmp/document_versions or env var)

    Returns:
        List of version history entries
    """
    import os
    import json
    from pathlib import Path

    storage_path = storage_dir or os.getenv("DOCUMENT_VERSION_STORAGE", "/tmp/document_versions")
    storage_dir_path = Path(storage_path)
    storage_dir_path.mkdir(parents=True, exist_ok=True)

    safe_document_id = _sanitize_document_id(document_id)
    history_file = storage_dir_path / f"{safe_document_id}.json"

    if not history_file.exists():
        logger.debug(f"No version history found for document {document_id}")
        return []

    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
        return history.get("versions", [])
    except Exception as e:
        logger.error(f"Failed to load version history for {document_id}: {e}", exc_info=True)
        return []


def get_latest_document_version(
    document_id: str,
    storage_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get the latest version of a document.

    Args:
        document_id: Document identifier
        storage_dir: Storage directory (default: /tmp/document_versions or env var)

    Returns:
        Latest version info or None
    """
    history = get_document_version_history(document_id, storage_dir)
    if not history:
        return None

    return history[-1]
