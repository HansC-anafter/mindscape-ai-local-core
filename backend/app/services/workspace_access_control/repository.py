"""Public repository composition; SQL responsibilities live in named mixins."""

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .repository_identity import AccessIdentityRepositoryMixin
from .repository_mutations import AccessMutationRepositoryMixin
from .repository_reads import AccessReadRepositoryMixin


class WorkspaceAccessControlRepository(
    AccessIdentityRepositoryMixin,
    AccessReadRepositoryMixin,
    AccessMutationRepositoryMixin,
    PostgresStoreBase,
):
    """Single public repository over one existing core PostgreSQL pool."""
