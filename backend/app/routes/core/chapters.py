"""
Chapter API routes
RESTful API for managing chapters derived from Intent structure

Chapters are derived from Intent metadata (chapter field),
grouping related intents by chapter identifier.
"""

import logging
from typing import List, Optional, Dict, Any
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ...models.mindscape import IntentCard, IntentStatus
from ...services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chapters"])

# Initialize store (singleton)
store = MindscapeStore()


# ============================================================================
# Request/Response Models
# ============================================================================


class IllustrationNeed(BaseModel):
    """Illustration need item"""

    intent_id: str
    type: str  # 'book_cover' | 'chapter_header' | 'social_media' | 'diagram' | 'icon'
    description: str
    style: Optional[str] = None
    status: str  # 'pending' | 'in_progress' | 'completed'
    artifact_id: Optional[str] = None


class ChapterResponse(BaseModel):
    """Chapter API response model"""

    id: str
    workspace_id: str
    title: str
    description: Optional[str] = None
    parent_intent_id: Optional[str] = None
    illustration_needs: List[IllustrationNeed] = Field(default_factory=list)


class ChapterIllustrationNeedsResponse(BaseModel):
    """Response for chapter illustration needs"""

    chapter_id: str
    illustration_needs: List[IllustrationNeed] = Field(default_factory=list)


class ListChaptersResponse(BaseModel):
    """Response model for listing chapters"""

    chapters: List[ChapterResponse]


# ============================================================================
# Helper Functions
# ============================================================================


def derive_chapters_from_intents(
    intents: List[IntentCard], workspace_id: str
) -> List[ChapterResponse]:
    """
    Derive chapters from Intent structure

    Groups intents by their metadata.chapter field and creates Chapter objects
    """
    # Group intents by chapter
    chapter_groups: Dict[str, List[IntentCard]] = defaultdict(list)

    for intent in intents:
        chapter_id = intent.metadata.get("chapter") if intent.metadata else None
        if chapter_id:
            chapter_groups[chapter_id].append(intent)

    # Build chapter responses
    chapters = []
    for chapter_id, chapter_intents in chapter_groups.items():
        # Find the primary intent (usually the one without parent or the first one)
        primary_intent = next(
            (i for i in chapter_intents if not i.parent_intent_id),
            chapter_intents[0] if chapter_intents else None,
        )

        if not primary_intent:
            continue

        # Extract illustration needs from intents
        illustration_needs: List[IllustrationNeed] = []

        for intent in chapter_intents:
            # Check if intent has illustration needs in metadata
            needs = (
                intent.metadata.get("illustration_needs") if intent.metadata else None
            )
            if needs and isinstance(needs, list):
                for need in needs:
                    illustration_needs.append(
                        IllustrationNeed(
                            intent_id=intent.id,
                            type=need.get("type", "diagram"),
                            description=need.get("description", ""),
                            style=need.get("style"),
                            status=need.get("status", "pending"),
                            artifact_id=need.get("artifact_id"),
                        )
                    )

        # Build chapter response
        chapter = ChapterResponse(
            id=chapter_id,
            workspace_id=workspace_id,
            title=primary_intent.title,  # Use primary intent title as chapter title
            description=primary_intent.description,
            parent_intent_id=primary_intent.id,
            illustration_needs=illustration_needs,
        )
        chapters.append(chapter)

    return chapters


def get_chapter_illustration_needs(
    chapter_id: str, intents: List[IntentCard]
) -> List[IllustrationNeed]:
    """
    Get illustration needs for a specific chapter
    """
    illustration_needs: List[IllustrationNeed] = []

    # Filter intents for this chapter
    chapter_intents = [
        intent
        for intent in intents
        if intent.metadata and intent.metadata.get("chapter") == chapter_id
    ]

    for intent in chapter_intents:
        needs = intent.metadata.get("illustration_needs") if intent.metadata else None
        if needs and isinstance(needs, list):
            for need in needs:
                illustration_needs.append(
                    IllustrationNeed(
                        intent_id=intent.id,
                        type=need.get("type", "diagram"),
                        description=need.get("description", ""),
                        style=need.get("style"),
                        status=need.get("status", "pending"),
                        artifact_id=need.get("artifact_id"),
                    )
                )

    return illustration_needs


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/workspaces/{workspace_id}/chapters")
async def list_chapters(workspace_id: str = Path(..., description="Workspace ID")):
    """
    List all chapters for a workspace

    Chapters are derived from Intent structure by grouping intents
    that have the same chapter identifier in their metadata.
    """
    try:
        # Get workspace to find owner_user_id (profile_id)
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        profile_id = workspace.owner_user_id

        # Get all intents for this profile
        intents = store.list_intents(profile_id=profile_id, status=None, priority=None)

        # Filter intents that belong to this workspace
        workspace_intents = []
        for intent in intents:
            intent_workspace_id = (
                intent.metadata.get("workspace_id") if intent.metadata else None
            )
            if intent_workspace_id == workspace_id or not intent_workspace_id:
                workspace_intents.append(intent)

        # Derive chapters from intents
        chapters = derive_chapters_from_intents(workspace_intents, workspace_id)

        return ListChaptersResponse(chapters=chapters)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to list chapters for workspace {workspace_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to list chapters: {str(e)}"
        )


@router.get("/chapters/{chapter_id}/illustration-needs")
async def get_chapter_illustration_needs(
    chapter_id: str = Path(..., description="Chapter ID"),
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """
    Get illustration needs for a specific chapter
    """
    try:
        # Get workspace to find owner_user_id (profile_id)
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        profile_id = workspace.owner_user_id

        # Get all intents for this profile
        intents = store.list_intents(profile_id=profile_id, status=None, priority=None)

        # Filter intents that belong to this workspace and chapter
        workspace_intents = []
        for intent in intents:
            intent_workspace_id = (
                intent.metadata.get("workspace_id") if intent.metadata else None
            )
            intent_chapter = intent.metadata.get("chapter") if intent.metadata else None

            if (
                intent_workspace_id == workspace_id or not intent_workspace_id
            ) and intent_chapter == chapter_id:
                workspace_intents.append(intent)

        # Get illustration needs
        illustration_needs = get_chapter_illustration_needs(
            chapter_id, workspace_intents
        )

        return ChapterIllustrationNeedsResponse(
            chapter_id=chapter_id, illustration_needs=illustration_needs
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get illustration needs for chapter {chapter_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get illustration needs: {str(e)}"
        )
