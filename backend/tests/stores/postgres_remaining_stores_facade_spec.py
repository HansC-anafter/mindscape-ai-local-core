from datetime import timezone

from backend.app.services.stores.postgres import remaining_stores
from backend.app.services.stores.postgres.commands_store import PostgresCommandsStore
from backend.app.services.stores.postgres.conversation_threads_store import (
    PostgresConversationThreadsStore,
)
from backend.app.services.stores.postgres.lens_composition_store import (
    PostgresLensCompositionStore,
)
from backend.app.services.stores.postgres.playbook_executions_store import (
    PostgresPlaybookExecutionsStore,
)
from backend.app.services.stores.postgres.surface_events_store import (
    PostgresSurfaceEventsStore,
)
from backend.app.services.stores.postgres.thread_references_store import (
    PostgresThreadReferencesStore,
)
from backend.app.services.stores.postgres.user_playbook_meta_store import (
    PostgresUserPlaybookMetaStore,
)


def test_remaining_stores_reexports_postgres_store_classes():
    assert remaining_stores.PostgresCommandsStore is PostgresCommandsStore
    assert (
        remaining_stores.PostgresConversationThreadsStore
        is PostgresConversationThreadsStore
    )
    assert remaining_stores.PostgresLensCompositionStore is PostgresLensCompositionStore
    assert remaining_stores.PostgresPlaybookExecutionsStore is PostgresPlaybookExecutionsStore
    assert remaining_stores.PostgresSurfaceEventsStore is PostgresSurfaceEventsStore
    assert remaining_stores.PostgresThreadReferencesStore is PostgresThreadReferencesStore
    assert remaining_stores.PostgresUserPlaybookMetaStore is PostgresUserPlaybookMetaStore


def test_remaining_stores_reexports_utc_now_helper():
    now = remaining_stores._utc_now()

    assert now.tzinfo is timezone.utc
