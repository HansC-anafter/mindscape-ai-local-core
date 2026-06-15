"""
Graph store for Mind-Lens Graph data persistence.

GraphStore remains the single public entrypoint. CRUD/query behavior lives in
focused mixins so the DB/session path is not duplicated.
"""

from typing import Optional

from app.services.stores.graph_lens_mixin import GraphLensMixin
from app.services.stores.graph_node_edge_mixin import GraphNodeEdgeMixin
from app.services.stores.postgres_base import PostgresStoreBase


class GraphStore(GraphNodeEdgeMixin, GraphLensMixin, PostgresStoreBase):
    """Store for managing graph nodes, edges, and lens profiles (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        # Keep db_path for backward compatibility (no longer used).
        self.db_path = db_path
