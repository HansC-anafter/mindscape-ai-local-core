"""Mind Lens service for CRUD operations."""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from ...models.mind_lens import MindLensSchema, MindLensInstance, RuntimeMindLens
from ...services.stores.postgres.mind_lens_store import PostgresMindLensStore

logger = logging.getLogger(__name__)


class MindLensService:
    """Service for managing Mind Lens schemas and instances."""

    def __init__(self, db_path: str = None):
        """
        Initialize Mind Lens service.

        Args:
            db_path: Optional database path (defaults to standard location)
        """
        self.store = PostgresMindLensStore()

    def create_schema(self, schema: MindLensSchema) -> MindLensSchema:
        """
        Create a new Mind Lens schema.

        Args:
            schema: Schema to create

        Returns:
            Created schema
        """
        return self.store.create_schema(schema)

    def get_schema(self, schema_id: str) -> Optional[MindLensSchema]:
        """
        Get schema by ID.

        Args:
            schema_id: Schema ID

        Returns:
            Schema or None if not found
        """
        return self.store.get_schema(schema_id)

    def get_schema_by_role(self, role: str) -> Optional[MindLensSchema]:
        """
        Get schema by role.

        Args:
            role: Role name

        Returns:
            Schema or None if not found
        """
        return self.store.get_schema_by_role(role)

    def create_instance(self, instance: MindLensInstance) -> MindLensInstance:
        """
        Create a new Mind Lens instance.

        Args:
            instance: Instance to create

        Returns:
            Created instance
        """
        return self.store.create_instance(instance)

    def get_instance(self, instance_id: str) -> Optional[MindLensInstance]:
        """
        Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance or None if not found
        """
        return self.store.get_instance(instance_id)

    def update_instance(
        self,
        instance_id: str,
        updates: dict
    ) -> Optional[MindLensInstance]:
        """
        Update instance.

        Args:
            instance_id: Instance ID
            updates: Update fields

        Returns:
            Updated instance or None if not found
        """
        return self.store.update_instance(instance_id, updates)

    def list_instances(
        self,
        owner_user_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50
    ) -> List[MindLensInstance]:
        """
        List instances with filters.

        Args:
            owner_user_id: Optional owner filter
            role: Optional role filter
            limit: Maximum number of results

        Returns:
            List of instances
        """
        return self.store.list_instances(owner_user_id=owner_user_id, role=role, limit=limit)

    def resolve_lens(
        self,
        user_id: str,
        workspace_id: str,
        playbook_id: Optional[str] = None,
        role_hint: Optional[str] = None
    ) -> Optional[RuntimeMindLens]:
        """
        Resolve Mind Lens for execution context.

        Args:
            user_id: User ID
            workspace_id: Workspace ID
            playbook_id: Optional playbook ID
            role_hint: Optional role hint

        Returns:
            Resolved RuntimeMindLens or None if not found
        """
        role = role_hint or "default"

        schema = self.store.get_schema_by_role(role)
        if not schema:
            logger.warning(f"No schema found for role: {role}")
            return None

        instances = self.store.list_instances(owner_user_id=user_id, role=role, limit=1)
        if not instances:
            logger.warning(f"No instance found for user {user_id} and role {role}")
            return None

        instance = instances[0]

        return RuntimeMindLens(
            resolved_mind_lens_id=f"resolved_{instance.mind_lens_id}",
            role=instance.role,
            source_lenses=[instance.mind_lens_id],
            values=instance.values,
            created_at=_utc_now()
        )






