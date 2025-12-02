"""
Canva API data schemas

Defines data structures for Canva API requests and responses.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class CanvaDesign(BaseModel):
    """Canva design representation"""

    id: str = Field(..., description="Design ID")
    title: str = Field(..., description="Design title")
    brand_id: Optional[str] = Field(None, description="Brand ID")
    template_id: Optional[str] = Field(None, description="Template ID if created from template")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    width: Optional[int] = Field(None, description="Design width in pixels")
    height: Optional[int] = Field(None, description="Design height in pixels")
    format: Optional[str] = Field(None, description="Design format")
    url: Optional[str] = Field(None, description="Design preview URL")


class CanvaTextBlock(BaseModel):
    """Canva text block representation"""

    id: str = Field(..., description="Text block ID")
    text: str = Field(..., description="Text content")
    x: Optional[float] = Field(None, description="X position")
    y: Optional[float] = Field(None, description="Y position")
    width: Optional[float] = Field(None, description="Block width")
    height: Optional[float] = Field(None, description="Block height")
    font_family: Optional[str] = Field(None, description="Font family")
    font_size: Optional[int] = Field(None, description="Font size")
    color: Optional[str] = Field(None, description="Text color")


class CanvaTemplate(BaseModel):
    """Canva template representation"""

    id: str = Field(..., description="Template ID")
    title: str = Field(..., description="Template title")
    description: Optional[str] = Field(None, description="Template description")
    brand_id: Optional[str] = Field(None, description="Brand ID")
    width: Optional[int] = Field(None, description="Template width")
    height: Optional[int] = Field(None, description="Template height")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL")


class TextBlockUpdate(BaseModel):
    """Text block update request"""

    block_id: str = Field(..., description="Text block ID to update")
    text: str = Field(..., description="New text content")


class CreateDesignRequest(BaseModel):
    """Create design from template request"""

    template_id: str = Field(..., description="Template ID")
    brand_id: Optional[str] = Field(None, description="Brand ID")
    title: Optional[str] = Field(None, description="Design title")


class UpdateTextBlocksRequest(BaseModel):
    """Update text blocks request"""

    design_id: str = Field(..., description="Design ID")
    text_blocks: List[TextBlockUpdate] = Field(..., description="List of text block updates")


class ExportDesignRequest(BaseModel):
    """Export design request"""

    design_id: str = Field(..., description="Design ID")
    format: str = Field(default="PNG", description="Export format (PNG, JPG, PDF)")
    scale: Optional[float] = Field(None, ge=0.1, le=4.0, description="Export scale factor")
