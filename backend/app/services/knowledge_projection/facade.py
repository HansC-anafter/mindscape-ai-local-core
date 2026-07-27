"""Facade module seam for every knowledge-foundation caller."""

from typing import Optional

from backend.app.services.knowledge_projection.group_context import (
    GroupKnowledgeContextReader,
)
from backend.app.services.knowledge_projection.projection import (
    KnowledgeProjectionService,
)
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    KnowledgeProjectionAdapterRegistry,
    get_adapter_registry,
)
from backend.app.services.knowledge_projection.retrievable.service import (
    RetrievableKnowledgeProjectionService,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    RetrievableSourceAdmissionService,
)
from backend.app.services.knowledge_projection.retrievable.coverage import (
    ProjectionCoverageService,
)
from backend.app.services.knowledge_projection.source_ledger import (
    KnowledgeSourceLedgerFacade,
)
from backend.app.services.knowledge_projection.synthesis import (
    GroupSynthesisCommitter,
    GroupSynthesisReviewService,
)


class KnowledgeProjectionFacade:
    """Expose one import seam while preserving single-purpose service owners."""

    def __init__(
        self,
        *,
        source_ledger: Optional[KnowledgeSourceLedgerFacade] = None,
        projection_service: Optional[KnowledgeProjectionService] = None,
        group_context_reader: Optional[GroupKnowledgeContextReader] = None,
        synthesis_committer: Optional[GroupSynthesisCommitter] = None,
        review_service: Optional[GroupSynthesisReviewService] = None,
        retrievable_adapter_registry: Optional[
            KnowledgeProjectionAdapterRegistry
        ] = None,
        retrievable_projection_service: Optional[
            RetrievableKnowledgeProjectionService
        ] = None,
        source_admission_service: Optional[
            RetrievableSourceAdmissionService
        ] = None,
        projection_coverage_service: Optional[
            ProjectionCoverageService
        ] = None,
    ) -> None:
        self.source_ledger = source_ledger or KnowledgeSourceLedgerFacade()
        self.projection_service = projection_service or KnowledgeProjectionService()
        self.group_context_reader = (
            group_context_reader or GroupKnowledgeContextReader()
        )
        self.synthesis_committer = synthesis_committer or GroupSynthesisCommitter()
        self.review_service = review_service or GroupSynthesisReviewService()
        self.retrievable_adapter_registry = (
            retrievable_adapter_registry or get_adapter_registry()
        )
        self.retrievable_projection_service = (
            retrievable_projection_service
            or RetrievableKnowledgeProjectionService()
        )
        self.source_admission_service = (
            source_admission_service
            or RetrievableSourceAdmissionService(
                registry=self.retrievable_adapter_registry
            )
        )
        self.projection_coverage_service = (
            projection_coverage_service or ProjectionCoverageService()
        )

    def record_source_intake(self, intake):
        return self.source_ledger.record_intake(intake)

    def project(self, request):
        return self.projection_service.project(request)

    def compile_group_packet(self, **kwargs):
        return self.group_context_reader.compile_packet(**kwargs)

    def commit_group_synthesis(self, handoff):
        return self.synthesis_committer.commit(handoff)

    def review_group_synthesis(self, command, **auth):
        return self.review_service.decide(command, **auth)

    def resolve_retrievable_adapter(self, **identity):
        return self.retrievable_adapter_registry.resolve(**identity)

    def list_retrievable_adapters(self, capability_code: str):
        return self.retrievable_adapter_registry.list_capability(capability_code)

    def project_retrievable(self, **kwargs):
        return self.retrievable_projection_service.project_retrievable(**kwargs)

    def revoke_retrievable(self, **kwargs):
        return self.retrievable_projection_service.revoke_retrievable(**kwargs)

    def admit_retrievable_source(self, command, **kwargs):
        return self.source_admission_service.admit(command, **kwargs)

    def admit_retrievable_source_page(self, commands, **kwargs):
        return self.source_admission_service.admit_page(
            tuple(commands),
            **kwargs,
        )

    def list_retrievable_coverage(self, **kwargs):
        return self.projection_coverage_service.list_page(**kwargs)
