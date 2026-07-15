"""Facade module seam for every knowledge-foundation caller."""

from typing import Optional

from backend.app.services.knowledge_projection.group_context import (
    GroupKnowledgeContextReader,
)
from backend.app.services.knowledge_projection.projection import (
    KnowledgeProjectionService,
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
    ) -> None:
        self.source_ledger = source_ledger or KnowledgeSourceLedgerFacade()
        self.projection_service = projection_service or KnowledgeProjectionService()
        self.group_context_reader = (
            group_context_reader or GroupKnowledgeContextReader()
        )
        self.synthesis_committer = synthesis_committer or GroupSynthesisCommitter()
        self.review_service = review_service or GroupSynthesisReviewService()

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
