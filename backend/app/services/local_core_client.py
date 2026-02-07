"""
Local Core Client
Client for interacting with local core services internally.
To replace missing module preventing backend startup.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import logging

# Try to import MindLensService, handle failure gracefully if also missing
try:
    from .lens.mind_lens_service import MindLensService
    from ..models.mind_lens import MindLensInstance
except ImportError:
    MindLensService = None
    MindLensInstance = None

logger = logging.getLogger(__name__)


class LocalCoreClient:
    """Client for internal service interactions."""

    def __init__(self):
        if MindLensService:
            self.mind_lens_service = MindLensService()
        else:
            self.mind_lens_service = None
            logger.warning("MindLensService not available for LocalCoreClient")

    async def create_mind_lens_instance(
        self,
        workspace_id: str,
        user_id: str,
        label: str,
        description: str,
        constraints: Dict[str, Any],
        syntax: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new Mind Lens instance."""

        instance_id = str(uuid.uuid4())

        if not self.mind_lens_service or not MindLensInstance:
            logger.warning(
                "Mocking create_mind_lens_instance because MindLensService is unavailable"
            )
            return {"lens_instance_id": instance_id, "status": "mocked"}

        # Create instance object
        # Note: Mapping workspace_id to source or metadata since model doesn't have it
        try:
            instance = MindLensInstance(
                mind_lens_id=instance_id,
                schema_id="default",  # Placeholder
                owner_user_id=user_id,
                role=metadata.get("role", "custom") if metadata else "custom",
                label=label,
                description=description,
                values={"constraints": constraints, "syntax": syntax},
                source={"workspace_id": workspace_id, "type": "preset"},
                metadata=metadata or {},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            result = self.mind_lens_service.create_instance(instance)

            # Return dict matching what preset_service expects
            return {"lens_instance_id": result.mind_lens_id, "status": "created"}
        except Exception as e:
            logger.error(f"Failed to create mind lens instance in LocalCoreClient: {e}")
            # Fallback to avoid crash
            return {"lens_instance_id": instance_id, "status": "fallback_error"}
