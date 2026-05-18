"""Router aggregation for sandbox routes."""

from .crud_routes import router as crud_router
from .file_routes import router as file_router
from .port_routes import router as port_router
from .preview_routes import router as preview_router
from .project_routes import router as project_router
from .sync_routes import router as sync_router
from .version_routes import router as version_router

router = crud_router
router.include_router(file_router)
router.include_router(version_router)
router.include_router(project_router)
router.include_router(preview_router)
router.include_router(sync_router)
router.include_router(port_router)
