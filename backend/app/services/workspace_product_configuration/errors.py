"""Stable WPC error types translated by the HTTP boundary."""


class WorkspaceProductConfigurationError(ValueError):
    code = "workspace_product_configuration_invalid"


class CatalogArtifactInvalidError(WorkspaceProductConfigurationError):
    code = "product_catalog_artifact_invalid"


class ActiveCatalogMissingError(WorkspaceProductConfigurationError):
    code = "active_product_catalog_missing"


class WorkspaceProductSnapshotLimitError(WorkspaceProductConfigurationError):
    code = "workspace_product_snapshot_size_limit_exceeded"


class CatalogRevisionConflictError(WorkspaceProductConfigurationError):
    code = "product_catalog_revision_conflict"

    def __init__(
        self,
        *,
        expected_catalog_hash: str,
        current_catalog_hash: str,
    ):
        self.expected_catalog_hash = expected_catalog_hash
        self.current_catalog_hash = current_catalog_hash
        super().__init__(
            f"expected catalog {expected_catalog_hash}, "
            f"current catalog {current_catalog_hash}"
        )


class ScopeAccessError(PermissionError):
    code = "workspace_product_scope_forbidden"


class ScopeRevisionConflictError(WorkspaceProductConfigurationError):
    code = "workspace_product_scope_revision_conflict"

    def __init__(
        self,
        *,
        expected_revision: int,
        actual_revision: int,
        current_catalog_hash: str,
    ):
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        self.current_catalog_hash = current_catalog_hash
        super().__init__(
            f"expected revision {expected_revision}, actual revision {actual_revision}"
        )


class TopologyRevisionConflictError(WorkspaceProductConfigurationError):
    code = "workspace_group_topology_revision_conflict"

    def __init__(self, *, expected_revision: int, actual_revision: int):
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"expected topology revision {expected_revision}, "
            f"actual revision {actual_revision}"
        )


class TopologyRevisionRequiredError(WorkspaceProductConfigurationError):
    code = "workspace_group_topology_revision_required"
