"""
Brand Context Helper API

Provides unified brand context for playbooks and other capabilities.
Supports both existing brand artifacts and on-the-fly generation from minimal data.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, TYPE_CHECKING
import logging
import sys
from pathlib import Path

if TYPE_CHECKING:
    from backend.app.services.mindscape_store import MindscapeStore
    from backend.app.services.stores.artifacts_store import ArtifactsStore

# Ensure cloud root is in sys.path for imports
current_file = Path(__file__)
cloud_root = current_file.parent.parent.parent.parent
if str(cloud_root) not in sys.path:
    sys.path.insert(0, str(cloud_root))

# Add local-core backend to path
local_core_backend = cloud_root.parent / "mindscape-ai-local-core" / "backend"
if str(local_core_backend) not in sys.path:
    sys.path.insert(0, str(local_core_backend))

# Import artifact store
try:
    from backend.app.services.stores.artifacts_store import ArtifactsStore
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from backend.app.services.mindscape_store import MindscapeStore
    ARTIFACT_STORE_AVAILABLE = True
except (ImportError, SyntaxError, IndentationError) as e:
    logging.warning(f"Artifact store not available ({type(e).__name__}): {e}")
    ARTIFACT_STORE_AVAILABLE = False
    # Define fallback types for type checking
    ArtifactsStore = None  # type: ignore
    Artifact = None  # type: ignore
    ArtifactType = None  # type: ignore
    PrimaryActionType = None  # type: ignore
    MindscapeStore = None  # type: ignore

# Import LLM provider
try:
    from backend.app.shared.llm_provider_helper import (
        build_managed_llm_provider,
    )
    LLM_PROVIDER_AVAILABLE = True
except (ImportError, SyntaxError, IndentationError) as e:
    logging.warning(f"LLM provider not available ({type(e).__name__}): {e}")
    LLM_PROVIDER_AVAILABLE = False
    build_managed_llm_provider = None  # type: ignore

logger = logging.getLogger(__name__)

# Initialize logger
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/api/v1/brand-identity/context", tags=["brand-identity", "context"])


class GetBrandContextRequest(BaseModel):
    """Request to get brand context for a workspace"""
    workspace_id: str
    auto_generate: bool = False  # If true, generate brand assets if not found
    min_data_required: bool = True  # Only generate if minimum data is available


class BrandContextResponse(BaseModel):
    """Response containing brand context"""
    has_brand_context: bool
    brand_mi: Optional[Dict[str, Any]] = None
    brand_personas: List[Dict[str, Any]] = []
    brand_storylines: List[Dict[str, Any]] = []
    brand_vi_rules: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


@router.post("/get", response_model=BrandContextResponse)
async def get_brand_context(request: GetBrandContextRequest) -> BrandContextResponse:
    """
    Get brand context for a workspace.

    If brand artifacts don't exist and auto_generate=True, attempts to generate
    basic brand assets from available workspace data.
    """
    if not ARTIFACT_STORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Artifact store not available"
        )

    try:
        store = MindscapeStore()
        artifacts_store = ArtifactsStore(store.db_path)

        # Try to get existing brand artifacts
        brand_mi_list = artifacts_store.list_artifacts_by_workspace(
            request.workspace_id,
            kind="brand_mi",
            limit=1
        )

        brand_personas_list = artifacts_store.list_artifacts_by_workspace(
            request.workspace_id,
            kind="brand_persona",
            limit=10
        )

        brand_storylines_list = artifacts_store.list_artifacts_by_workspace(
            request.workspace_id,
            kind="brand_storyline",
            limit=10
        )

        brand_vi_rules_list = artifacts_store.list_artifacts_by_workspace(
            request.workspace_id,
            kind="brand_vi_rule",
            limit=1
        )

        # If we have brand artifacts, return them
        if brand_mi_list:
            brand_mi = brand_mi_list[0]
            brand_personas = brand_personas_list
            brand_storylines = brand_storylines_list
            brand_vi_rules = brand_vi_rules_list[0] if brand_vi_rules_list else None

            return BrandContextResponse(
                has_brand_context=True,
                brand_mi=brand_mi.content if hasattr(brand_mi, 'content') else brand_mi.get('content'),
                brand_personas=[p.content if hasattr(p, 'content') else p.get('content') for p in brand_personas],
                brand_storylines=[s.content if hasattr(s, 'content') else s.get('content') for s in brand_storylines],
                brand_vi_rules=brand_vi_rules.content if brand_vi_rules and hasattr(brand_vi_rules, 'content') else (brand_vi_rules.get('content') if brand_vi_rules else None),
                metadata={
                    "source": "existing_artifacts",
                    "brand_mi_id": brand_mi.id if hasattr(brand_mi, 'id') else brand_mi.get('id'),
                    "persona_count": len(brand_personas),
                    "storyline_count": len(brand_storylines)
                }
            )

        # If no brand artifacts and auto_generate is enabled
        if request.auto_generate:
            # Try to generate from available workspace data
            generated_context = await _generate_brand_context_from_workspace(
                request.workspace_id,
                store,
                artifacts_store,
                min_data_required=request.min_data_required
            )

            if generated_context:
                return generated_context

        # No brand context available
        return BrandContextResponse(
            has_brand_context=False,
            metadata={
                "source": "none",
                "suggestion": "Run 'cis_mind_identity' playbook to create brand assets"
            }
        )

    except Exception as e:
        logger.error(f"Failed to get brand context: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get brand context: {str(e)}"
        )


async def _generate_brand_context_from_workspace(
    workspace_id: str,
    store: "MindscapeStore",
    artifacts_store: "ArtifactsStore",
    min_data_required: bool = True
) -> Optional[BrandContextResponse]:
    """
    Generate basic brand context from available workspace data.

    Minimum data required:
    - workspace.title (required)
    - workspace.description (optional but helpful)
    - Any existing artifacts or content in the workspace

    Returns None if minimum data is not available.
    """
    try:
        # Get workspace
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            return None

        # Check minimum data requirement
        if min_data_required:
            if not workspace.title or len(workspace.title.strip()) < 3:
                logger.info(f"Workspace {workspace_id} doesn't have enough data for brand context generation")
                return None

        # Collect available data
        available_data = {
            "workspace_title": workspace.title,
            "workspace_description": workspace.description or "",
            "workspace_type": workspace.workspace_type.value if workspace.workspace_type else None
        }

        # Try to collect additional context from existing artifacts
        all_artifacts = artifacts_store.list_artifacts_by_workspace(workspace_id, limit=50)
        if all_artifacts:
            # Extract text snippets from artifacts for context
            artifact_texts = []
            for artifact in all_artifacts[:10]:  # Limit to first 10 for context
                if hasattr(artifact, 'summary'):
                    artifact_texts.append(artifact.summary or "")
                elif isinstance(artifact, dict):
                    artifact_texts.append(artifact.get('summary', ''))

            available_data["artifact_summaries"] = artifact_texts

        # Check if we have enough data
        data_quality = _assess_data_quality(available_data)

        if data_quality["score"] < 0.3 and min_data_required:
            logger.info(f"Data quality too low for generation: {data_quality}")
            return None

        # Generate basic brand assets using LLM
        if not LLM_PROVIDER_AVAILABLE:
            logger.warning("LLM provider not available, cannot generate brand context")
            return None

        generated_assets = await _generate_basic_brand_assets(
            available_data,
            workspace_id,
            artifacts_store,
            workspace=workspace,
        )

        if generated_assets:
            return BrandContextResponse(
                has_brand_context=True,
                brand_mi=generated_assets.get("brand_mi"),
                brand_personas=generated_assets.get("brand_personas", []),
                brand_storylines=generated_assets.get("brand_storylines", []),
                brand_vi_rules=None,  # VI requires more data, skip for now
                metadata={
                    "source": "auto_generated",
                    "data_quality_score": data_quality["score"],
                    "data_quality_details": data_quality,
                    "note": "These are auto-generated brand assets. Consider running 'cis_mind_identity' playbook for more comprehensive brand definition."
                }
            )

        return None

    except Exception as e:
        logger.error(f"Failed to generate brand context from workspace: {e}", exc_info=True)
        return None


def _assess_data_quality(available_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assess the quality of available data for brand context generation.

    Returns a score (0.0 to 1.0) and details about what data is available.
    """
    score = 0.0
    details = {}

    # Workspace title (required, 0.3 points)
    if available_data.get("workspace_title"):
        title_len = len(available_data["workspace_title"].strip())
        if title_len >= 3:
            score += 0.3
            details["has_title"] = True
            details["title_length"] = title_len
        else:
            details["has_title"] = False

    # Workspace description (helpful, 0.2 points)
    if available_data.get("workspace_description"):
        desc_len = len(available_data["workspace_description"].strip())
        if desc_len >= 20:
            score += 0.2
            details["has_description"] = True
            details["description_length"] = desc_len
        else:
            details["has_description"] = False

    # Workspace type (helpful, 0.1 points)
    if available_data.get("workspace_type") == "brand":
        score += 0.1
        details["is_brand_workspace"] = True
    else:
        details["is_brand_workspace"] = False

    # Artifact summaries (very helpful, 0.4 points)
    artifact_summaries = available_data.get("artifact_summaries", [])
    if artifact_summaries:
        total_text = " ".join(artifact_summaries)
        text_len = len(total_text.strip())
        if text_len >= 100:
            score += 0.4
            details["has_artifact_context"] = True
            details["artifact_text_length"] = text_len
            details["artifact_count"] = len(artifact_summaries)
        else:
            details["has_artifact_context"] = False

    return {
        "score": min(score, 1.0),
        "details": details,
        "sufficient": score >= 0.3  # Minimum threshold
    }


async def _generate_basic_brand_assets(
    available_data: Dict[str, Any],
    workspace_id: str,
    artifacts_store: ArtifactsStore,
    workspace: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate basic brand assets (MI, Personas, Storylines) from minimal data.

    Minimum viable data:
    - workspace.title (required)
    - workspace.description (optional but helpful)
    - Some artifact content (optional but helpful)

    Returns generated assets dict or None if generation fails.
    """
    if not LLM_PROVIDER_AVAILABLE:
        return None

    try:
        if not build_managed_llm_provider:
            return None

        try:
            llm_provider, selection = build_managed_llm_provider(
                workspace=workspace,
                purpose="brand_identity.auto_generate",
            )
        except Exception as exc:
            logger.info(
                "Skipping auto-generated brand context without explicit managed "
                "LLM selection: %s",
                exc,
            )
            return None

        # Build prompt for minimal brand asset generation
        prompt = f"""Based on the following minimal information, generate basic brand assets.

Workspace Information:
- Title: {available_data.get('workspace_title', 'Unknown')}
- Description: {available_data.get('workspace_description', 'No description')}
- Type: {available_data.get('workspace_type', 'unknown')}

Additional Context:
{chr(10).join(available_data.get('artifact_summaries', [])[:3]) if available_data.get('artifact_summaries') else 'No additional context'}

Generate a minimal but useful brand context with:
1. Brand MI (Mind Identity):
   - vision: A brief vision statement (1-2 sentences)
   - values: 3-5 core values (short phrases)
   - worldview: A brief worldview statement (1-2 sentences)
   - redlines: 2-3 basic redlines (what the brand won't do)

2. Brand Personas (2-3 personas):
   - name: Persona name
   - description: Brief description
   - needs: 2-3 key needs
   - pain_points: 2-3 pain points

3. Brand Storylines (2-3 storylines):
   - theme: Storyline theme
   - description: Brief description
   - key_messages: 2-3 key messages

Return JSON in this format:
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

        messages = [{"role": "user", "content": prompt}]
        response = await llm_provider.chat_completion(
            messages=messages,
            model=selection.model_name,
            temperature=0.7,
            max_tokens=2048
        )

        # Extract JSON from response
        llm_output = response if isinstance(response, str) else (
            response.content if hasattr(response, 'content') else
            response.choices[0].message.content if hasattr(response, 'choices') and len(response.choices) > 0 else ""
        )

        # Parse JSON (similar to cis_mapper_endpoints.py)
        import json
        json_text = llm_output.strip()

        # Extract JSON block if wrapped in markdown
        if "```json" in json_text:
            start_idx = json_text.find("```json") + 7
            end_idx = json_text.find("```", start_idx)
            if end_idx != -1:
                json_text = json_text[start_idx:end_idx].strip()
        elif "```" in json_text:
            start_idx = json_text.find("```") + 3
            end_idx = json_text.find("```", start_idx)
            if end_idx != -1:
                json_text = json_text[start_idx:end_idx].strip()

        # Find JSON object
        if not json_text.startswith("{"):
            start_brace = json_text.find("{")
            if start_brace != -1:
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
                    json_text = json_text[start_brace:end_brace + 1]

        json_text = json_text.strip()

        if not json_text or not json_text.startswith("{"):
            logger.error(f"Could not extract valid JSON from LLM response: {llm_output[:500]}")
            return None

        extracted_data = json.loads(json_text)

        # Format as brand assets
        brand_assets = {
            "brand_mi": extracted_data.get("brand_mi", {}),
            "brand_personas": extracted_data.get("personas", []),
            "brand_storylines": extracted_data.get("storylines", [])
        }

        # Optionally save as artifacts (if requested)
        # For now, just return the generated assets without saving
        # The caller can decide whether to persist them

        return brand_assets

    except Exception as e:
        logger.error(f"Failed to generate basic brand assets: {e}", exc_info=True)
        return None
