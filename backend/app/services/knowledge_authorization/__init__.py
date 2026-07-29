"""Public authorization-aware knowledge contracts and context factory."""

from .access_context_factory import (
    RetrievalAccessContextFactory,
    RetrievalScopeDenied,
    VerifiedAgentExecution,
)
from .contracts import (
    AgentExecutionMask,
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    ScopeMembership,
)
from .context_sql import set_local_knowledge_context
from .service import (
    KnowledgeAuthorizationService,
    KnowledgeReadAdmission,
    KnowledgeWriteForbiddenError,
)
from .store import (
    KnowledgeAuthorizationConflictError,
    KnowledgeAuthorizationStore,
    visibility_partition_hash_for_grants,
)
from .write_contracts import (
    KnowledgeAclMutation,
    KnowledgeGrant,
    KnowledgeResourceBinding,
    KnowledgeResourceIdentity,
)

__all__ = [
    "AgentExecutionMask",
    "KnowledgeAclMutation",
    "KnowledgeAuthorizationConflictError",
    "KnowledgeAuthorizationService",
    "KnowledgeAuthorizationStore",
    "KnowledgeGrant",
    "KnowledgePermission",
    "KnowledgeReadAdmission",
    "KnowledgeResourceBinding",
    "KnowledgeResourceIdentity",
    "KnowledgeWriteForbiddenError",
    "PrincipalRef",
    "RetrievalAccessContext",
    "set_local_knowledge_context",
    "RetrievalAccessContextFactory",
    "RetrievalScopeDenied",
    "ScopeMembership",
    "VerifiedAgentExecution",
    "visibility_partition_hash_for_grants",
]
