"""
CIS Mapper API endpoints.

Maps unstructured brand documents to structured CIS artifacts (MI, Persona, Storyline).
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import os
import json
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

# Initialize logger first before any imports that might use it
logger = logging.getLogger(__name__)

# Import multi-platform LLM adapter
# Note: These imports are resolved at module load time by api_loader.py
# which adds the cloud root to sys.path before importing this module
import sys
from pathlib import Path

# Ensure cloud root is in sys.path for imports
current_file = Path(__file__)
# From: capabilities/brand_identity/api/cis_mapper_endpoints.py
# To: mindscape-ai-cloud (4 levels up: api -> brand_identity -> capabilities -> cloud_root)
cloud_root = current_file.parent.parent.parent.parent
if str(cloud_root) not in sys.path:
    sys.path.insert(0, str(cloud_root))

# Import after sys.path is set
# Direct import from file to avoid circular import through __init__.py
# The __init__.py imports task_router which imports PLATFORM_ADAPTERS which imports claude_adapter
# This creates a circular dependency when claude_adapter imports from ..core
import importlib.util

# Import local-core LLM provider management instead of hardcoding provider
# Use local-core's stable LLM provider routing mechanism
import sys
from pathlib import Path

# Add local-core backend to path to import LLM provider helpers
current_file = Path(__file__)
cloud_root = current_file.parent.parent.parent.parent
local_core_backend = cloud_root.parent / "mindscape-ai-local-core" / "backend"
if str(local_core_backend) not in sys.path:
    sys.path.insert(0, str(local_core_backend))

try:
    from backend.app.shared.llm_provider_helper import (
        build_managed_llm_provider,
    )
except ImportError as e:
    logger.warning(f"Failed to import local-core LLM provider helpers: {e}")
    # Fallback: will handle in the endpoint
    build_managed_llm_provider = None

from services.site_hub_client import SiteHubClient

# Import local-core artifact store to save artifacts
try:
    from backend.app.services.stores.artifacts_store import ArtifactsStore
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType

    ARTIFACT_STORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Artifact store not available: {e}")
    ARTIFACT_STORE_AVAILABLE = False

router = APIRouter(
    prefix="/api/v1/brand-identity/cis-mapper", tags=["brand-identity", "cis-mapper"]
)
_api_key_cache: dict = {}


class DocumentInput(BaseModel):
    """Single document input for multi-document processing."""

    content: Optional[str] = None  # Text content (if already extracted)
    file_path: Optional[str] = None  # File path (for images, PDFs, etc.)
    file_url: Optional[str] = None  # File URL (optional)
    type: Optional[str] = (
        None  # Document type (interview, brief, presentation, image, pdf, etc.)
    )
    title: Optional[str] = None  # Document title
    priority: Optional[int] = None  # Priority score (auto-calculated if not provided)
    mime_type: Optional[str] = None  # File MIME type


class MapDocumentRequest(BaseModel):
    """Request to map a brand document to CIS artifacts."""

    document_content: str
    document_type: Optional[str] = None  # e.g., "interview", "brief", "presentation"
    workspace_id: str
    target_language: Optional[str] = "zh-TW"


class MapMultipleDocumentsRequest(BaseModel):
    """Request to map multiple brand documents to CIS artifacts."""

    documents: List[DocumentInput]
    workspace_id: str
    merge_strategy: str = (
        "sequential"  # sequential, parallel (hierarchical not yet implemented)
    )
    target_language: Optional[str] = "zh-TW"
    max_documents: Optional[int] = 10  # Maximum number of documents to process
    auto_select: bool = True  # Automatically select most relevant documents if too many
    auto_start_ocr: bool = True  # Auto-start OCR service if not running
    enable_version_tracking: bool = True  # Enable document version tracking (Phase 4)


class IncrementalMapRequest(BaseModel):
    """Request for incremental document processing."""

    document_id: str  # Document identifier for version tracking
    old_content: Optional[str] = None  # Previous version content
    old_file_path: Optional[str] = None  # Previous version file path
    new_content: str  # New version content
    new_file_path: Optional[str] = None  # New version file path
    workspace_id: str
    document_type: Optional[str] = None
    target_language: Optional[str] = "zh-TW"
    existing_artifacts: Optional[List[Dict[str, Any]]] = (
        None  # Existing artifacts to merge with
    )


class CISArtifactData(BaseModel):
    """Structured CIS artifact data."""

    kind: str  # "brand_mi", "brand_persona", "brand_storyline"
    title: str
    summary: str
    content: Dict[str, Any]


class MapDocumentResponse(BaseModel):
    """Response containing mapped CIS artifacts."""

    artifacts: List[CISArtifactData]
    metadata: Dict[str, Any]


class MapMultipleDocumentsResponse(BaseModel):
    """Response containing mapped CIS artifacts from multiple documents."""

    artifacts: List[CISArtifactData]
    metadata: Dict[str, Any]
    processing_summary: Dict[str, Any]
    ocr_usage: Optional[Dict[str, Any]] = None  # OCR usage statistics


@router.post("/map", response_model=MapDocumentResponse)
async def map_document_to_cis(request: MapDocumentRequest) -> MapDocumentResponse:
    """
    Map a brand document to structured CIS artifacts.

    This capability analyzes unstructured brand documents (interviews, briefs, presentations)
    and extracts structured CIS data:
    - Brand Mind Identity (MI): Vision, Values, Worldview, Redlines
    - Brand Persona: Target audience personas
    - Brand Storyline: Core narrative themes

    Args:
        request: Document content and metadata

    Returns:
        List of structured CIS artifacts ready for creation
    """
    try:
        logger.info(
            f"CIS Mapper: Processing document (type={request.document_type}, workspace={request.workspace_id})"
        )

        if not build_managed_llm_provider:
            raise HTTPException(
                status_code=500,
                detail="LLM provider management not available. Please ensure local-core backend is accessible.",
            )

        try:
            llm_provider, selection = build_managed_llm_provider(
                purpose="brand_identity.cis_mapper",
            )
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=(
                    "CIS mapper requires an explicit chat_model selection in Settings. "
                    f"{str(e)}"
                ),
            ) from e

        provider_name = selection.provider_name or (
            llm_provider.__class__.__name__.replace("Provider", "").lower()
        )
        model_name = selection.model_name
        logger.info(
            "Using explicit chat_model provider=%s model=%s for CIS extraction",
            provider_name,
            model_name,
        )

        language = request.target_language or "zh-TW"
        lang_instruction = "繁體中文" if language.startswith("zh") else "English"

        prompt = f"""請分析以下品牌文檔，提取 CIS（Corporate Identity System）資訊。

文檔類型：{request.document_type or "未指定"}
文檔內容：
{request.document_content}

請提取以下資訊，並以 JSON 格式返回：

1. **Brand MI (Mind Identity - 品牌心智識別)**：
   - vision: 品牌願景（一段話）
   - values: 品牌價值觀（陣列，至少 3-5 個）
   - worldview: 品牌世界觀（一段話，描述品牌如何看待世界）
   - redlines: 品牌紅線（陣列，品牌絕對不能做的事或說的話）

2. **Brand Personas (品牌受眾畫像)**：
   - 至少提取 1-3 個主要受眾
   - 每個 persona 包含：
     - name: 受眾名稱
     - description: 受眾描述（一段話）
     - needs: 受眾需求（陣列）
     - pain_points: 痛點（陣列，可選）

3. **Brand Storylines (品牌故事主軸)**：
   - 至少提取 1-3 個核心故事主軸
   - 每個 storyline 包含：
     - theme: 主題名稱
     - description: 故事主軸描述（一段話）
     - key_messages: 關鍵訊息（陣列，可選）

請以以下 JSON 格式返回（使用 {lang_instruction}）：
{{
  "brand_mi": {{
    "vision": "...",
    "values": ["...", "..."],
    "worldview": "...",
    "redlines": ["...", "..."]
  }},
  "personas": [
    {{
      "name": "...",
      "description": "...",
      "needs": ["...", "..."],
      "pain_points": ["...", "..."]
    }}
  ],
  "storylines": [
    {{
      "theme": "...",
      "description": "...",
      "key_messages": ["...", "..."]
    }}
  ]
}}"""

        logger.info(
            "Calling %s API for CIS extraction (model: %s)...",
            provider_name,
            model_name,
        )

        # Use local-core LLM provider's chat_completion method
        messages = [{"role": "user", "content": prompt}]

        response = await llm_provider.chat_completion(
            messages=messages,
            model=model_name,
            temperature=0.3,
            max_tokens=4096,
        )

        # Extract text from response
        # local-core LLM providers return string directly
        if isinstance(response, str):
            llm_output = response
        elif hasattr(response, "content"):
            llm_output = response.content
        elif hasattr(response, "choices") and len(response.choices) > 0:
            llm_output = response.choices[0].message.content
        else:
            logger.error(
                f"Unexpected LLM response format: {type(response)}, response: {response}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected LLM response format: {type(response)}",
            )

        if not llm_output or not llm_output.strip():
            logger.error(f"Empty LLM response: {response}")
            raise HTTPException(status_code=500, detail="LLM returned empty response")

        logger.info(
            f"LLM response received (length: {len(llm_output)}, preview: {llm_output[:200]}...)"
        )

        # Extract JSON from response (may contain explanatory text before/after JSON)
        json_text = llm_output.strip()

        if not json_text:
            raise HTTPException(
                status_code=500, detail="LLM returned empty response after processing"
            )

        # Strategy 1: Try to extract JSON block if wrapped in markdown code blocks
        if "```json" in json_text:
            # Extract content between ```json and ```
            start_idx = json_text.find("```json") + 7
            end_idx = json_text.find("```", start_idx)
            if end_idx != -1:
                json_text = json_text[start_idx:end_idx].strip()
        elif "```" in json_text:
            # Extract content between ``` and ```
            start_idx = json_text.find("```") + 3
            end_idx = json_text.find("```", start_idx)
            if end_idx != -1:
                json_text = json_text[start_idx:end_idx].strip()

        # Strategy 2: Find JSON object in the text (look for { ... })
        if not json_text.startswith("{"):
            # Find first { and matching }
            start_brace = json_text.find("{")
            if start_brace != -1:
                # Find matching closing brace by counting braces
                brace_count = 0
                end_brace = -1
                for i in range(start_brace, len(json_text)):
                    if json_text[i] == "{":
                        brace_count += 1
                    elif json_text[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_brace = i
                            break
                if end_brace != -1:
                    json_text = json_text[start_brace : end_brace + 1]

        json_text = json_text.strip()

        # Final validation
        if not json_text or not json_text.startswith("{"):
            logger.error(
                f"Could not extract valid JSON from LLM response. Preview: {llm_output[:500]}"
            )
            raise HTTPException(
                status_code=500,
                detail="LLM response does not contain valid JSON. Please check the prompt or LLM output.",
            )

        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.error(f"Response text: {json_text[:500]}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse LLM response as JSON: {str(e)}",
            )

        artifacts = []

        if "brand_mi" in extracted_data:
            mi_data = extracted_data["brand_mi"]
            artifacts.append(
                CISArtifactData(
                    kind="brand_mi",
                    title="Brand Mind Identity",
                    summary=f"Brand vision, values, worldview, and redlines extracted from {request.document_type or 'document'}",
                    content={
                        "vision": mi_data.get("vision", ""),
                        "values": mi_data.get("values", []),
                        "worldview": mi_data.get("worldview", ""),
                        "redlines": mi_data.get("redlines", []),
                    },
                )
            )

        if "personas" in extracted_data:
            for persona_data in extracted_data["personas"]:
                artifacts.append(
                    CISArtifactData(
                        kind="brand_persona",
                        title=f"Persona: {persona_data.get('name', 'Unknown')}",
                        summary=persona_data.get("description", "")[:200],
                        content={
                            "name": persona_data.get("name", ""),
                            "description": persona_data.get("description", ""),
                            "needs": persona_data.get("needs", []),
                            "pain_points": persona_data.get("pain_points", []),
                        },
                    )
                )

        if "storylines" in extracted_data:
            for storyline_data in extracted_data["storylines"]:
                artifacts.append(
                    CISArtifactData(
                        kind="brand_storyline",
                        title=f"Storyline: {storyline_data.get('theme', 'Unknown')}",
                        summary=storyline_data.get("description", "")[:200],
                        content={
                            "theme": storyline_data.get("theme", ""),
                            "description": storyline_data.get("description", ""),
                            "key_messages": storyline_data.get("key_messages", []),
                        },
                    )
                )

        if not artifacts:
            raise HTTPException(
                status_code=500,
                detail="No artifacts extracted from document. LLM response may be invalid.",
            )

        logger.info(f"Successfully extracted {len(artifacts)} artifacts from document")

        # Save artifacts to database if artifact store is available
        created_artifact_ids = []
        if ARTIFACT_STORE_AVAILABLE:
            try:
                # Get database path from MindscapeStore (same as artifacts API route)
                from backend.app.services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                artifact_store = ArtifactsStore(store.db_path)

                # Map CIS artifact kinds to ArtifactType
                # Use DATA type for structured CIS artifacts
                artifact_type_map = {
                    "brand_mi": ArtifactType.DATA,
                    "brand_persona": ArtifactType.DATA,
                    "brand_storyline": ArtifactType.DATA,
                }

                for cis_artifact in artifacts:
                    artifact_type = artifact_type_map.get(
                        cis_artifact.kind, ArtifactType.DATA
                    )

                    artifact = Artifact(
                        id=str(uuid.uuid4()),
                        workspace_id=request.workspace_id,
                        intent_id=None,
                        task_id=None,
                        execution_id=None,
                        playbook_code="cis_mapper",  # Source capability
                        artifact_type=artifact_type,
                        title=cis_artifact.title,
                        summary=cis_artifact.summary,
                        content=cis_artifact.content,
                        storage_ref=None,
                        sync_state=None,
                        primary_action_type=PrimaryActionType.PREVIEW,  # Default action for viewing artifacts
                        metadata={
                            "source": "cis_mapper_api",
                            "document_type": request.document_type,
                            "llm_model": model_name,
                            "llm_provider": provider_name,
                        },
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                    )

                    created_artifact = artifact_store.create_artifact(artifact)
                    created_artifact_ids.append(created_artifact.id)
                    logger.info(
                        f"Created artifact: {created_artifact.id} ({cis_artifact.kind})"
                    )

                logger.info(
                    f"Successfully saved {len(created_artifact_ids)} artifacts to database"
                )
            except Exception as e:
                import traceback

                error_trace = traceback.format_exc()
                logger.warning(
                    f"Failed to save artifacts to database: {e}\n{error_trace}"
                )
                # Continue even if saving fails - artifacts are still in response

        return MapDocumentResponse(
            artifacts=artifacts,
            metadata={
                "document_type": request.document_type,
                "processed_at": _utc_now().isoformat(),
                "version": "v1",
                "llm_model": model_name,
                "llm_provider": provider_name,
                "artifacts_saved": (
                    len(created_artifact_ids) if ARTIFACT_STORE_AVAILABLE else 0
                ),
                "artifact_ids": (
                    created_artifact_ids if ARTIFACT_STORE_AVAILABLE else []
                ),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to map document to CIS: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
        raise HTTPException(
            status_code=500, detail=f"Failed to map document: {error_detail}"
        )


@router.post("/map-multiple", response_model=MapMultipleDocumentsResponse)
async def map_multiple_documents(
    request: MapMultipleDocumentsRequest,
) -> MapMultipleDocumentsResponse:
    """
    Map multiple brand documents to structured CIS artifacts.

    This endpoint processes multiple documents (text, images, PDFs) and extracts
    brand information, then merges the results into unified CIS artifacts.

    Args:
        request: Multiple documents and processing configuration

    Returns:
        Merged CIS artifacts from all documents
    """
    import time

    start_time = time.time()

    try:
        logger.info(
            f"CIS Mapper: Processing {len(request.documents)} documents (workspace={request.workspace_id})"
        )

        # Validate merge_strategy
        supported_strategies = ["sequential", "parallel"]
        if request.merge_strategy not in supported_strategies:
            logger.warning(
                f"Unsupported merge_strategy '{request.merge_strategy}', "
                f"falling back to 'sequential'. Supported: {supported_strategies}"
            )
            request.merge_strategy = "sequential"

        # Import utility functions
        # Use relative imports since we're in the same package
        try:
            from .utils.ocr_utils import (
                extract_text_from_file,
                is_multimodal_document,
                ensure_ocr_service_running,
            )
            from .utils.document_selection import (
                select_relevant_documents,
                get_document_priority,
            )

            # Use local-core document processor for length checking and chunking
            from backend.app.services.document_processor import (
                check_document_length,
                chunk_document_to_objects,
            )
            from .utils.chunking_utils import chunk_document_semantic

            # Phase 4: Version tracking utilities
            if request.enable_version_tracking:
                from .utils.version_utils import track_document_version
        except (ImportError, SyntaxError, IndentationError) as e:
            logger.warning(
                f"Local-core document_processor not available ({type(e).__name__}), using cloud-side fallback: {e}"
            )
            # Import cloud-side utilities that should still work
            from .utils.ocr_utils import (
                extract_text_from_file,
                is_multimodal_document,
                ensure_ocr_service_running,
            )
            from .utils.document_selection import (
                select_relevant_documents,
                get_document_priority,
            )
            from .utils.chunking_utils import (
                chunk_document_semantic,
                DocumentChunk,
                chunk_document_by_paragraphs,
                chunk_document_by_sentences,
            )
            from .utils.document_utils import (
                check_document_length as cloud_check_length,
            )

            if request.enable_version_tracking:
                from .utils.version_utils import track_document_version

            # Define fallback implementations for local-core functions
            def check_document_length(
                content: str,
                model: str = "claude-3-5-sonnet",
                buffer_ratio: float = 0.2,
            ):
                """Cloud-side fallback for check_document_length"""
                return cloud_check_length(content, model, buffer_ratio)

            def chunk_document_to_objects(
                content: str, max_chunk_size: int = 100000, strategy: str = "paragraph"
            ):
                """Cloud-side fallback for chunk_document_to_objects"""
                if strategy == "sentence":
                    chunk_strings = chunk_document_by_sentences(content, max_chunk_size)
                else:
                    chunk_strings = chunk_document_by_paragraphs(
                        content, max_chunk_size
                    )

                document_chunks = []
                current_index = 0
                for i, chunk_content in enumerate(chunk_strings):
                    start_index = current_index
                    end_index = current_index + len(chunk_content)
                    chunk = DocumentChunk(
                        content=chunk_content,
                        start_index=start_index,
                        end_index=end_index,
                        chunk_index=i,
                    )
                    document_chunks.append(chunk)
                    current_index = end_index
                return document_chunks

        # Check OCR service if needed
        ocr_used = False
        ocr_documents_count = 0
        needs_ocr = any(
            doc.file_path and is_multimodal_document(doc.file_path)
            for doc in request.documents
        )

        if needs_ocr:
            if not await ensure_ocr_service_running(auto_start=request.auto_start_ocr):
                logger.warning(
                    "OCR service not available, skipping multimodal documents"
                )
            else:
                ocr_used = True

        # Process multimodal documents (extract text)
        processed_documents = []
        processing_errors = []  # Initialize error tracking
        for doc in request.documents:
            processed_doc = doc.model_dump() if hasattr(doc, "model_dump") else doc

            # If file_path provided and no content, extract text
            if doc.file_path and not doc.content:
                if is_multimodal_document(doc.file_path):
                    if ocr_used:
                        try:
                            extracted_text = await extract_text_from_file(doc.file_path)
                            if not extracted_text or not extracted_text.strip():
                                error_msg = f"OCR extraction returned empty content for {doc.file_path}"
                                logger.error(error_msg)
                                processing_errors.append(
                                    {
                                        "document_title": doc.title or doc.file_path,
                                        "error": error_msg,
                                        "error_type": "ocr_empty_result",
                                    }
                                )
                                continue  # Skip this document
                            processed_doc["content"] = extracted_text
                            processed_doc["ocr_extracted"] = True
                            ocr_documents_count += 1
                        except Exception as e:
                            error_msg = (
                                f"Failed to extract text from {doc.file_path}: {e}"
                            )
                            logger.error(error_msg)
                            processing_errors.append(
                                {
                                    "document_title": doc.title or doc.file_path,
                                    "error": error_msg,
                                    "error_type": "ocr_extraction_failed",
                                }
                            )
                            continue  # Skip this document instead of setting empty content
                    else:
                        # OCR not available, mark as error
                        error_msg = f"OCR service not available for multimodal document {doc.file_path}"
                        logger.warning(error_msg)
                        processing_errors.append(
                            {
                                "document_title": doc.title or doc.file_path,
                                "error": error_msg,
                                "error_type": "ocr_service_unavailable",
                            }
                        )
                        continue  # Skip this document
                else:
                    # Regular text file, read directly
                    try:
                        with open(doc.file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            if not content or not content.strip():
                                error_msg = f"File {doc.file_path} is empty"
                                logger.warning(error_msg)
                                processing_errors.append(
                                    {
                                        "document_title": doc.title or doc.file_path,
                                        "error": error_msg,
                                        "error_type": "file_empty",
                                    }
                                )
                                continue
                            processed_doc["content"] = content
                    except Exception as e:
                        error_msg = f"Failed to read file {doc.file_path}: {e}"
                        logger.error(error_msg)
                        processing_errors.append(
                            {
                                "document_title": doc.title or doc.file_path,
                                "error": error_msg,
                                "error_type": "file_read_error",
                            }
                        )
                        continue  # Skip this document
            elif not doc.content:
                error_msg = (
                    f"Document {doc.title or doc.file_path or 'unknown'} has no content"
                )
                logger.warning(error_msg)
                processing_errors.append(
                    {
                        "document_title": doc.title or doc.file_path or "unknown",
                        "error": error_msg,
                        "error_type": "no_content",
                    }
                )
                continue  # Skip this document

            # Only add documents with valid content
            if processed_doc.get("content") and processed_doc["content"].strip():
                # Phase 4: Track document version if enabled
                if request.enable_version_tracking and doc.file_path:
                    try:
                        document_id = f"{request.workspace_id}:{doc.file_path}"
                        track_document_version(
                            document_id,
                            processed_doc["content"],
                            metadata={
                                "file_path": doc.file_path,
                                "title": doc.title,
                                "type": doc.type,
                            },
                            persist=True,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to track version for {doc.file_path}: {e}"
                        )
                        # Don't fail the whole request if version tracking fails

                # Calculate priority if not provided
                if processed_doc.get("priority") is None:
                    processed_doc["priority"] = get_document_priority(
                        processed_doc.get("type")
                    )

                processed_documents.append(processed_doc)

        # Document selection (if too many)
        if request.auto_select and len(processed_documents) > request.max_documents:
            logger.info(
                f"Selecting top {request.max_documents} documents from {len(processed_documents)}"
            )
            selected_docs = select_relevant_documents(
                processed_documents,
                max_count=request.max_documents,
                prioritize_by_type=True,
            )
            processed_documents = selected_docs

        # Process documents (sequential or parallel based on strategy)
        all_artifacts = []

        if request.merge_strategy == "parallel":
            # Parallel processing (Phase 6)
            try:
                from .utils.parallel_utils import process_documents_parallel

                async def process_single_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
                    """Process a single document"""
                    if not doc.get("content"):
                        return {"artifacts": [], "error": "No content"}

                    try:
                        length_check = check_document_length(doc["content"])
                        if length_check["needs_chunking"]:
                            chunks = chunk_document_semantic(
                                doc["content"],
                                max_chunk_size=int(
                                    length_check["available_tokens"] * 1.3
                                ),
                            )
                            chunk_artifacts = []
                            for chunk in chunks:
                                chunk_result = await map_document_to_cis(
                                    MapDocumentRequest(
                                        document_content=chunk.content,
                                        document_type=doc.get("type"),
                                        workspace_id=request.workspace_id,
                                        target_language=request.target_language,
                                    )
                                )
                                chunk_artifacts.extend(chunk_result.artifacts)
                            return {"artifacts": chunk_artifacts, "error": None}
                        else:
                            result = await map_document_to_cis(
                                MapDocumentRequest(
                                    document_content=doc["content"],
                                    document_type=doc.get("type"),
                                    workspace_id=request.workspace_id,
                                    target_language=request.target_language,
                                )
                            )
                            return {"artifacts": result.artifacts, "error": None}
                    except Exception as e:
                        logger.error(f"Failed to process document: {e}")
                        return {"artifacts": [], "error": str(e)}

                parallel_results = await process_documents_parallel(
                    processed_documents, process_single_doc, max_workers=5
                )

                for i, result in enumerate(parallel_results):
                    if result.get("error"):
                        processing_errors.append(
                            {
                                "document_index": i,
                                "document_title": processed_documents[i].get(
                                    "title", "unknown"
                                ),
                                "error": result["error"],
                            }
                        )
                    else:
                        all_artifacts.extend(result.get("artifacts", []))

            except ImportError:
                logger.warning(
                    "Parallel utils not available, falling back to sequential"
                )
                request.merge_strategy = "sequential"

        # Sequential processing (default or fallback)
        if request.merge_strategy == "sequential":
            for i, doc in enumerate(processed_documents):
                if not doc.get("content"):
                    logger.warning(f"Skipping document {i+1} - no content")
                    continue

                try:
                    logger.info(
                        f"Processing document {i+1}/{len(processed_documents)}: {doc.get('title', 'unknown')}"
                    )

                    # Check document length and chunk if needed
                    length_check = check_document_length(doc["content"])
                    if length_check["needs_chunking"]:
                        logger.info(
                            f"Document {i+1} exceeds context limit, chunking..."
                        )
                        # Convert available_tokens to characters (rough estimate)
                        # Use a conservative ratio: 1 token ≈ 1.3 characters for Chinese
                        max_chunk_chars = int(length_check["available_tokens"] * 1.3)

                        # Try semantic-aware chunking first (Cloud capability)
                        try:
                            chunks = chunk_document_semantic(
                                doc["content"], max_chunk_size=max_chunk_chars
                            )
                        except Exception as e:
                            logger.warning(
                                f"Semantic chunking failed, using basic chunking: {e}"
                            )
                            # Fallback to local-core basic chunking
                            chunks = chunk_document_to_objects(
                                doc["content"],
                                max_chunk_size=max_chunk_chars,
                                strategy="paragraph",
                            )

                        # Process each chunk and merge results
                        chunk_artifacts = []
                        for chunk in chunks:
                            chunk_result = await map_document_to_cis(
                                MapDocumentRequest(
                                    document_content=chunk.content,
                                    document_type=doc.get("type"),
                                    workspace_id=request.workspace_id,
                                    target_language=request.target_language,
                                )
                            )
                            chunk_artifacts.extend(chunk_result.artifacts)
                        # Merge chunk artifacts (simple merge for now)
                        all_artifacts.extend(chunk_artifacts)
                    else:
                        # Process normally
                        result = await map_document_to_cis(
                            MapDocumentRequest(
                                document_content=doc["content"],
                                document_type=doc.get("type"),
                                workspace_id=request.workspace_id,
                                target_language=request.target_language,
                            )
                        )
                        all_artifacts.extend(result.artifacts)

                except Exception as e:
                    logger.error(
                        f"Failed to process document {i+1}: {e}", exc_info=True
                    )
                    processing_errors.append(
                        {
                            "document_index": i,
                            "document_title": doc.get("title", "unknown"),
                            "error": str(e),
                        }
                    )

        # Merge artifacts using Phase 3 advanced merging
        merged_artifacts = _merge_artifacts_simple(all_artifacts)

        processing_time = time.time() - start_time

        return MapMultipleDocumentsResponse(
            artifacts=merged_artifacts,
            metadata={
                "documents_processed": len(processed_documents),
                "documents_total": len(request.documents),
                "merge_strategy": request.merge_strategy,
                "processing_time": round(processing_time, 2),
                "errors": processing_errors if processing_errors else None,
                "version": "v1",
            },
            processing_summary={
                "total_documents": len(request.documents),
                "processed_documents": len(processed_documents),
                "total_artifacts": len(all_artifacts),
                "merged_artifacts": len(merged_artifacts),
                "processing_time_seconds": round(processing_time, 2),
                "errors_count": len(processing_errors),
            },
            ocr_usage=(
                {
                    "ocr_used": ocr_used,
                    "ocr_documents_count": ocr_documents_count,
                    "ocr_service_available": ocr_used,
                }
                if ocr_used
                else None
            ),
        )

    except Exception as e:
        logger.error(f"Failed to map multiple documents: {e}", exc_info=True)
        error_detail = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
        raise HTTPException(
            status_code=500, detail=f"Failed to map multiple documents: {error_detail}"
        )


def _merge_artifacts_simple(artifacts: List[CISArtifactData]) -> List[CISArtifactData]:
    """
    Simple artifact merging strategy.

    Uses Phase 3 merge utilities for advanced merging with deduplication.

    Args:
        artifacts: List of artifacts from all documents

    Returns:
        Merged artifacts list
    """
    # Convert CISArtifactData to dict format for merge_utils
    artifacts_dict = []
    for artifact in artifacts:
        artifacts_dict.append(
            {
                "kind": artifact.kind,
                "title": artifact.title,
                "summary": artifact.summary,
                "content": artifact.content,
            }
        )

    # Use Phase 3 merge utilities
    try:
        from .utils.merge_utils import merge_cis_artifacts

        merged_dicts = merge_cis_artifacts(artifacts_dict, similarity_threshold=0.7)

        # Convert back to CISArtifactData
        merged_artifacts = []
        for merged_dict in merged_dicts:
            merged_artifacts.append(
                CISArtifactData(
                    kind=merged_dict["kind"],
                    title=merged_dict["title"],
                    summary=merged_dict["summary"],
                    content=merged_dict["content"],
                )
            )

        return merged_artifacts
    except ImportError as e:
        logger.warning(f"Merge utilities not available, using simple merge: {e}")
        # Fallback to simple merge
        merged_mi = None
        personas = []
        storylines = []
        other_artifacts = []

        for artifact in artifacts:
            if artifact.kind == "brand_mi":
                if not merged_mi or len(str(artifact.content)) > len(
                    str(merged_mi.content)
                ):
                    merged_mi = artifact
            elif artifact.kind == "brand_persona":
                personas.append(artifact)
            elif artifact.kind == "brand_storyline":
                storylines.append(artifact)
            else:
                other_artifacts.append(artifact)

        merged = []
        if merged_mi:
            merged.append(merged_mi)
        merged.extend(personas)
        merged.extend(storylines)
        merged.extend(other_artifacts)

        return merged


@router.post("/map-incremental", response_model=MapDocumentResponse)
async def map_document_incremental(
    request: IncrementalMapRequest,
) -> MapDocumentResponse:
    """
    Incrementally process document updates.

    This endpoint processes only the changed sections of a document,
    extracting brand information from updates and merging with existing artifacts.

    Strategy:
    1. Load previous version (from file or provided content)
    2. Detect changed sections using diff analysis
    3. Extract brand info only from changed sections
    4. Merge with existing artifacts
    """
    import time

    start_time = time.time()

    # Use local-core document processor for version tracking
    try:
        from backend.app.services.document_processor import (
            detect_document_changes,
            calculate_content_hash,
        )

        # Version tracking functions (still in Cloud for now, but use local-core for change detection)
        from .utils.version_utils import (
            track_document_version,
            get_latest_document_version,
        )
    except (ImportError, SyntaxError, IndentationError) as e:
        logger.warning(
            f"Local-core document_processor not available ({type(e).__name__}), using Cloud fallback: {e}"
        )
        # Fallback to Cloud version_utils if local-core not available
        from .utils.version_utils import (
            track_document_version,
            get_latest_document_version,
            detect_document_changes,
        )
    from .utils.incremental_utils import (
        incremental_extract_cis_artifacts,
        merge_incremental_cis_artifacts,
    )
    from .utils.ocr_utils import extract_text_from_file

    try:
        # Load old content
        old_content = request.old_content
        if not old_content and request.old_file_path:
            old_content = await extract_text_from_file(request.old_file_path)
        elif not old_content:
            # Try to load from version history
            latest_version = get_latest_document_version(request.document_id)
            if latest_version and latest_version.get("metadata", {}).get("content"):
                old_content = latest_version["metadata"]["content"]
            else:
                logger.warning(
                    f"No old content found for document {request.document_id}, performing full extraction"
                )
                old_content = None

        # Load new content
        new_content = request.new_content
        if not new_content and request.new_file_path:
            new_content = await extract_text_from_file(request.new_file_path)

        if not new_content:
            raise HTTPException(
                status_code=400,
                detail="Either new_content or new_file_path must be provided",
            )

        # Track new version
        version_info = track_document_version(
            request.document_id,
            new_content,
            metadata={"content": new_content, "file_path": request.new_file_path},
            persist=True,
        )

        # If no old content, perform full extraction
        if not old_content:
            logger.info("No old content found, performing full extraction")
            result = await map_document_to_cis(
                MapDocumentRequest(
                    document_content=new_content,
                    document_type=request.document_type,
                    workspace_id=request.workspace_id,
                    target_language=request.target_language,
                )
            )
            return result

        # Incremental extraction
        existing_artifacts = request.existing_artifacts or []

        # Define extract function for changed sections
        async def extract_from_content(content: str) -> List[Dict[str, Any]]:
            """Extract artifacts from content"""
            result = await map_document_to_cis(
                MapDocumentRequest(
                    document_content=content,
                    document_type=request.document_type,
                    workspace_id=request.workspace_id,
                    target_language=request.target_language,
                )
            )
            # Use model_dump() for Pydantic v2, fallback to dict() for v1
            return [
                (
                    artifact.model_dump()
                    if hasattr(artifact, "model_dump")
                    else artifact.model_dump()
                )
                for artifact in result.artifacts
            ]

        incremental_cis_artifacts = await incremental_extract_cis_artifacts(
            old_content,
            new_content,
            existing_artifacts,
            extract_cis_func=extract_from_content,
        )

        # If incremental extraction returned empty, perform full extraction
        if not incremental_cis_artifacts:
            logger.info("Incremental CIS extraction signaled full re-extraction")
            result = await map_document_to_cis(
                MapDocumentRequest(
                    document_content=new_content,
                    document_type=request.document_type,
                    workspace_id=request.workspace_id,
                    target_language=request.target_language,
                )
            )
            return result

        # Merge incremental CIS results
        if existing_artifacts:
            merged_artifacts = merge_incremental_cis_artifacts(
                existing_artifacts, incremental_cis_artifacts
            )
        else:
            merged_artifacts = incremental_cis_artifacts

        # Convert to CISArtifactData
        artifacts = [CISArtifactData(**artifact) for artifact in merged_artifacts]

        processing_time = time.time() - start_time

        return MapDocumentResponse(
            artifacts=artifacts,
            metadata={
                "document_id": request.document_id,
                "processing_mode": "incremental",
                "processing_time": round(processing_time, 2),
                "version_hash": version_info["content_hash"][:8],
            },
        )

    except Exception as e:
        logger.error(f"Failed to process document incrementally: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process document incrementally: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "capability": "cis_mapper"}


class PackageLensRequest(BaseModel):
    """Request to package a brand lens."""

    workspace_id: str
    cis_components: Dict[str, Any]
    lens_id: Optional[str] = None


@router.post("/package-lens")
async def package_lens(request: PackageLensRequest) -> Dict[str, Any]:
    """
    Package CIS components into a standardized Brand Lens artifact.

    Args:
        request: CIS components and metadata

    Returns:
        Packaged Brand Lens artifact
    """
    try:
        if not request.lens_id:
            request.lens_id = str(uuid.uuid4())

        cis_data = request.cis_components

        # Standardize structure
        brand_lens = {
            "lens_pack_version": "1.0.0",
            "lens_id": request.lens_id,
            "workspace_id": request.workspace_id,
            "persona": cis_data.get("persona", {}),
            "storyline": cis_data.get("storyline", {}),
            "visual_identity": cis_data.get("visual_identity", {}),
            "mind_identity": cis_data.get("brand_mi", {}),
            "meta": {
                "created_at": _utc_now().isoformat(),
                "source": "cis_mapper",
            },
        }

        # Save artifact if store available
        if ARTIFACT_STORE_AVAILABLE:
            try:
                from backend.app.services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                artifact_store = ArtifactsStore(store.db_path)

                artifact = Artifact(
                    id=str(uuid.uuid4()),
                    workspace_id=request.workspace_id,
                    artifact_type=ArtifactType.DATA,
                    title=f"Brand Lens: {cis_data.get('brand_mi', {}).get('vision', 'Untitled')[:30]}",
                    summary="Standardized Brand Lens package",
                    content=brand_lens,
                    playbook_code="cis_lens_packaging",
                    primary_action_type=PrimaryActionType.PREVIEW,
                    metadata={"lens_id": request.lens_id},
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )

                artifact_store.create_artifact(artifact)
                logger.info(f"Saved Brand Lens artifact {artifact.id}")
            except Exception as e:
                logger.warning(f"Failed to save Brand Lens artifact: {e}")

        return brand_lens

    except Exception as e:
        logger.error(f"Failed to package brand lens: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to package lens: {str(e)}")
