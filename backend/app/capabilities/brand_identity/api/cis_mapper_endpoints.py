from fastapi import APIRouter

from .cis_mapper_mapping_routes import router as mapping_router
from .cis_mapper_models import (
    CISArtifactData,
    DocumentInput,
    IncrementalMapRequest,
    MapDocumentRequest,
    MapDocumentResponse,
    MapMultipleDocumentsRequest,
    MapMultipleDocumentsResponse,
    PackageLensRequest,
)
from .cis_mapper_packaging_routes import router as packaging_router

router = APIRouter(
    prefix="/cis-mapper", tags=["brand-identity", "cis-mapper"]
)
router.include_router(mapping_router)
router.include_router(packaging_router)

__all__ = [
    "CISArtifactData",
    "DocumentInput",
    "IncrementalMapRequest",
    "MapDocumentRequest",
    "MapDocumentResponse",
    "MapMultipleDocumentsRequest",
    "MapMultipleDocumentsResponse",
    "PackageLensRequest",
    "router",
]
