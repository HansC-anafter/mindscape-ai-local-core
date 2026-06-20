from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


TOUCHED_FILES = [
    "backend/app/services/chat_orchestrator_service.py",
    "backend/app/services/chat_orchestrator_core/__init__.py",
    "backend/app/services/chat_orchestrator_core/events.py",
    "backend/app/services/chat_orchestrator_core/agent_dispatch.py",
    "backend/app/services/chat_orchestrator_core/llm_path.py",
    "backend/tests/chat_orchestrator_service_seams_spec.py",
]

PRODUCTION_FILES = [path for path in TOUCHED_FILES if not path.startswith("backend/tests/")]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_canonical_callers_still_use_chat_orchestrator_service():
    caller_paths = [
        "backend/features/workspace/chat/routes.py",
        "backend/app/services/meeting_command_dispatch_chat.py",
        "backend/app/services/cloud_connector/messaging_workspace_dispatch.py",
    ]
    for path in caller_paths:
        source = read_source(path)
        assert "chat_orchestrator_service" in source
        assert "ChatOrchestratorService" in source


def test_facade_keeps_public_methods_and_no_heavy_helper_ownership():
    source = read_source("backend/app/services/chat_orchestrator_service.py")

    required_fragments = [
        "class ChatOrchestratorService",
        "async def run_background_chat",
        "async def _handle_agent_dispatch",
        "async def _handle_llm_path",
        "async def _create_pipeline_event",
        "async def _create_error_event",
        "return pipeline_result",
    ]
    for fragment in required_fragments:
        assert fragment in source

    moved_fragments = [
        "WorkspaceAgentExecutor",
        "stream_llm_response",
        "build_streaming_context",
        "PostgresTimelineItemsStore",
        "self.orchestrator.store.create_event",
    ]
    for fragment in moved_fragments:
        assert fragment not in source


def test_event_persistence_has_single_helper_owner():
    event_source = read_source("backend/app/services/chat_orchestrator_core/events.py")
    service_source = read_source("backend/app/services/chat_orchestrator_service.py")
    agent_source = read_source("backend/app/services/chat_orchestrator_core/agent_dispatch.py")
    llm_source = read_source("backend/app/services/chat_orchestrator_core/llm_path.py")

    for fragment in [
        "run_in_executor",
        "store.create_event",
        "EventType.PIPELINE_STAGE",
        "EventType.MESSAGE",
        '"is_error"',
        '"retry_data"',
    ]:
        assert fragment in event_source

    assert "run_in_executor" not in service_source
    assert "run_in_executor" not in agent_source
    assert "run_in_executor" not in llm_source


def test_agent_and_llm_helpers_preserve_critical_contracts():
    agent_source = read_source("backend/app/services/chat_orchestrator_core/agent_dispatch.py")
    llm_source = read_source("backend/app/services/chat_orchestrator_core/llm_path.py")

    for fragment in [
        "WorkspaceAgentExecutor",
        "build_streaming_context",
        "PostgresTimelineItemsStore",
        '"uploaded_files"',
        '"execution_time"',
        "Runtime substitution is disabled.",
    ]:
        assert fragment in agent_source

    for fragment in [
        "stream_llm_response",
        "get_llm_provider",
        "db_path=orchestrator_store.db_path",
        "build_workspace_instruction_block",
        "SGRReasoningService",
        "context_token_count",
    ]:
        assert fragment in llm_source


def test_touched_files_stay_under_large_file_gate_and_language_rules():
    forbidden_resource_fragments = [
        "Queue(",
        "Thread(",
        "Process(",
        "create_engine(",
        "pgbouncer",
        "setInterval",
        "EventSource",
    ]
    for relative_path in TOUCHED_FILES:
        path = ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        line_count = source.count("\n")
        assert line_count <= 500, f"{relative_path} has {line_count} lines"
        assert not any("\u4e00" <= char <= "\u9fff" for char in source)
    for relative_path in PRODUCTION_FILES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in forbidden_resource_fragments:
            assert fragment not in source
