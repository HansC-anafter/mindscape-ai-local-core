from ..services.lens.effective_lens_resolver import EffectiveLensResolver
from ..services.lens.session_override_store import InMemorySessionStore
from ..services.stores.graph_store import GraphStore


def get_graph_store() -> GraphStore:
    """Get graph store instance"""
    return GraphStore()


_session_store = InMemorySessionStore()


def get_lens_resolver() -> EffectiveLensResolver:
    """Get effective lens resolver instance"""
    graph_store = get_graph_store()
    return EffectiveLensResolver(graph_store, _session_store)
