"""Lens Composition service for CRUD operations."""
from typing import Optional, List
from datetime import datetime
import logging
import os

from ...models.lens_composition import LensComposition
from ...services.stores.lens_composition_store import LensCompositionStore

logger = logging.getLogger(__name__)


class CompositionService:
    """Service for managing Lens Compositions."""

    def __init__(self, db_path: str = None):
        """
        Initialize composition service.

        Args:
            db_path: Optional database path (defaults to standard location)
        """
        if db_path is None:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                from pathlib import Path
                base_dir = Path(__file__).parent.parent.parent.parent.parent
                data_dir = base_dir / "data"
                data_dir.mkdir(exist_ok=True)
                db_path = str(data_dir / "mindscape.db")

        self.store = LensCompositionStore(db_path)

    def create_composition(self, composition: LensComposition) -> LensComposition:
        """
        Create a new composition.

        Args:
            composition: Composition to create

        Returns:
            Created composition
        """
        return self.store.create_composition(composition)

    def get_composition(self, composition_id: str) -> Optional[LensComposition]:
        """
        Get composition by ID.

        Args:
            composition_id: Composition ID

        Returns:
            Composition or None if not found
        """
        return self.store.get_composition(composition_id)

    def update_composition(
        self,
        composition_id: str,
        updates: dict
    ) -> Optional[LensComposition]:
        """
        Update composition.

        Args:
            composition_id: Composition ID
            updates: Update fields

        Returns:
            Updated composition or None if not found
        """
        return self.store.update_composition(composition_id, updates)

    def delete_composition(self, composition_id: str) -> bool:
        """
        Delete composition.

        Args:
            composition_id: Composition ID

        Returns:
            True if deleted, False if not found
        """
        return self.store.delete_composition(composition_id)

    def list_compositions(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 50
    ) -> List[LensComposition]:
        """
        List compositions.

        Args:
            workspace_id: Optional workspace filter
            limit: Maximum number of results

        Returns:
            List of compositions
        """
        return self.store.list_compositions(workspace_id=workspace_id, limit=limit)

