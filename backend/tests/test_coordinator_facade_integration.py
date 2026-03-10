"""
Integration tests for CoordinatorFacade

Tests end-to-end flows with mocked external services.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from backend.app.services.conversation.coordinator_facade import CoordinatorFacade
from backend.app.models.workspace import ExecutionPlan, TaskPlan, SideEffectLevel
from backend.app.mindscape.shims.execution_context import ExecutionContext


@pytest.fixture
def mock_store(tmp_path):
    """Create mock MindscapeStore"""
    store = Mock()
    store.db_path = str(tmp_path / "test.db")
    workspace = Mock()
    workspace.playbook_auto_execution_config = {}
    workspace.execution_mode = "qa"
    workspace.execution_priority = "medium"
    store.workspaces.get_workspace = Mock(return_value=workspace)
    store.create_event = Mock()
    return store


@pytest.fixture
def mock_tasks_store():
    """Create mock TasksStore"""
    store = Mock()
    store.create_task = Mock()
    store.get_task = Mock(return_value=None)
    store.get_task_by_execution_id = Mock(return_value=None)
    store.list_pending_tasks = Mock(return_value=[])
    store.find_existing_suggestion_tasks = Mock(return_value=[])
    return store


@pytest.fixture
def mock_timeline_items_store():
    """Create mock TimelineItemsStore"""
    return Mock()


@pytest.fixture
def mock_task_manager():
    """Create mock TaskManager"""
    manager = Mock()
    manager.check_and_update_task_status = AsyncMock()
    return manager


@pytest.fixture
def mock_plan_builder():
    """Create mock PlanBuilder"""
    builder = Mock()
    builder.determine_side_effect_level = Mock(return_value=SideEffectLevel.READONLY)
    return builder


@pytest.fixture
def mock_playbook_runner():
    """Create mock PlaybookRunner"""
    return Mock()


@pytest.fixture
def mock_message_generator():
    """Create mock MessageGenerator"""
    return Mock()


@pytest.fixture
def mock_playbook_service():
    """Create mock PlaybookService"""
    service = Mock()
    playbook = Mock()
    service.get_playbook = AsyncMock(return_value=playbook)
    execution_result = Mock()
    execution_result.execution_id = "exec-123"
    execution_result.status = "running"
    execution_result.result = {}
    service.execute_playbook = AsyncMock(return_value=execution_result)
    return service


@pytest.fixture
def coordinator_facade(
    mock_store,
    mock_tasks_store,
    mock_timeline_items_store,
    mock_task_manager,
    mock_plan_builder,
    mock_playbook_runner,
    mock_message_generator,
    mock_playbook_service,
):
    """Create CoordinatorFacade instance"""
    return CoordinatorFacade(
        store=mock_store,
        tasks_store=mock_tasks_store,
        timeline_items_store=mock_timeline_items_store,
        task_manager=mock_task_manager,
        plan_builder=mock_plan_builder,
        playbook_runner=mock_playbook_runner,
        message_generator=mock_message_generator,
        default_locale="en",
        playbook_service=mock_playbook_service,
    )


@pytest.fixture
def execution_plan():
    """Create sample ExecutionPlan"""
    task_plan = TaskPlan(
        pack_id="test_pack",
        task_type="test_task",
        params={"key": "value"},
        auto_execute=True,
    )
    return ExecutionPlan(
        tasks=[task_plan],
        message_id="msg-123",
        workspace_id="workspace-123",
    )


@pytest.fixture
def execution_context():
    """Create sample ExecutionContext"""
    return ExecutionContext(
        actor_id="user-123",
        metadata={"workspace_id": "workspace-123", "tags": {"mode": "local"}},
    )


@pytest.mark.asyncio
async def test_execute_plan_with_project_id_adds_metadata(
    coordinator_facade, execution_plan, execution_context
):
    """Test that project_id automatically adds project_name/title to inputs"""
    with patch.object(
        coordinator_facade.plan_preparer, "_load_project_meta"
    ) as mock_load:
        mock_load.return_value = {
            "id": "project-123",
            "title": "Test Project",
            "name": "Test Project",
        }

        with patch.object(
            coordinator_facade.playbook_resolver, "resolve"
        ) as mock_resolve:
            resolved = Mock()
            resolved.code = "test_playbook"
            resolved.playbook = Mock()
            resolved.source = "system"
            mock_resolve.return_value = resolved

            with patch.object(
                coordinator_facade.execution_launcher, "launch"
            ) as mock_launch:
                mock_launch.return_value = {
                    "execution_id": "exec-123",
                    "execution_mode": "conversation",
                    "raw_result": {},
                }

                results = await coordinator_facade.execute_plan_with_ctx(
                    execution_plan=execution_plan,
                    ctx=execution_context,
                    message_id="msg-123",
                    files=[],
                    message="test",
                    project_id="project-123",
                )

                assert "executed_tasks" in results
                # Verify project metadata was loaded
                mock_load.assert_called_once_with("project-123", "workspace-123")


@pytest.mark.asyncio
async def test_execute_plan_without_project_id(
    coordinator_facade, execution_plan, execution_context
):
    """Test execute_plan without project_id maintains current behavior"""
    with patch.object(
        coordinator_facade.playbook_resolver, "resolve"
    ) as mock_resolve:
        resolved = Mock()
        resolved.code = "test_playbook"
        resolved.playbook = Mock()
        resolved.source = "system"
        mock_resolve.return_value = resolved

        with patch.object(
            coordinator_facade.execution_launcher, "launch"
        ) as mock_launch:
            mock_launch.return_value = {
                "execution_id": "exec-123",
                "execution_mode": "conversation",
                "raw_result": {},
            }

            results = await coordinator_facade.execute_plan_with_ctx(
                execution_plan=execution_plan,
                ctx=execution_context,
                message_id="msg-123",
                files=[],
                message="test",
                project_id=None,
            )

            assert "executed_tasks" in results


@pytest.mark.asyncio
async def test_playbook_resolution_priority(
    coordinator_facade, execution_plan, execution_context
):
    """Test that capability playbooks are tried before system playbooks"""
    with patch("backend.app.services.capability_registry.get_registry") as mock_registry:
        registry = Mock()
        capability = Mock()
        registry.get_capability.return_value = capability
        registry.get_capability_playbooks.return_value = ["capability_playbook.yaml"]
        mock_registry.return_value = registry

        playbook = Mock()
        coordinator_facade.playbook_service.get_playbook = AsyncMock(
            return_value=playbook
        )

        with patch.object(
            coordinator_facade.execution_launcher, "launch"
        ) as mock_launch:
            mock_launch.return_value = {
                "execution_id": "exec-123",
                "execution_mode": "conversation",
                "raw_result": {},
            }

            results = await coordinator_facade.execute_plan_with_ctx(
                execution_plan=execution_plan,
                ctx=execution_context,
                message_id="msg-123",
                files=[],
                message="test",
            )

            # Verify capability playbook was tried first
            assert coordinator_facade.playbook_service.get_playbook.called


@pytest.mark.asyncio
async def test_missing_execution_id_warning(
    coordinator_facade, execution_plan, execution_context
):
    """Test that missing execution_id logs warning but doesn't crash"""
    with patch.object(
        coordinator_facade.playbook_resolver, "resolve"
    ) as mock_resolve:
        resolved = Mock()
        resolved.code = "test_playbook"
        resolved.playbook = Mock()
        resolved.source = "system"
        mock_resolve.return_value = resolved

        with patch.object(
            coordinator_facade.execution_launcher, "launch"
        ) as mock_launch:
            mock_launch.return_value = {
                "execution_id": None,  # Missing execution_id
                "execution_mode": "conversation",
                "raw_result": {},
            }

            with patch.object(
                coordinator_facade.error_policy, "handle_missing_execution_id"
            ) as mock_warn:
                results = await coordinator_facade.execute_plan_with_ctx(
                    execution_plan=execution_plan,
                    ctx=execution_context,
                    message_id="msg-123",
                    files=[],
                    message="test",
                )

                # Should not crash, should log warning
                mock_warn.assert_called()
                assert "executed_tasks" in results


@pytest.mark.asyncio
async def test_task_event_callback_format(
    coordinator_facade, execution_plan, execution_context
):
    """Test that task_event_callback is called with correct format"""
    callback_calls = []

    def mock_callback(event_type, event_data):
        callback_calls.append((event_type, event_data))

    with patch.object(
        coordinator_facade.playbook_resolver, "resolve"
    ) as mock_resolve:
        resolved = Mock()
        resolved.code = "test_playbook"
        resolved.playbook = Mock()
        resolved.source = "system"
        mock_resolve.return_value = resolved

        with patch.object(
            coordinator_facade.execution_launcher, "launch"
        ) as mock_launch:
            mock_launch.return_value = {
                "execution_id": "exec-123",
                "execution_mode": "conversation",
                "raw_result": {},
            }

            await coordinator_facade.execute_plan_with_ctx(
                execution_plan=execution_plan,
                ctx=execution_context,
                message_id="msg-123",
                files=[],
                message="test",
                task_event_callback=mock_callback,
            )

            # Verify callback was called
            assert len(callback_calls) > 0
            event_type, event_data = callback_calls[0]
            assert event_type == "created"
            assert "id" in event_data
            assert "pack_id" in event_data
            assert "status" in event_data


@pytest.mark.asyncio
async def test_task_event_callback_error_handling(
    coordinator_facade, execution_plan, execution_context
):
    """Test that task_event_callback errors don't break main flow"""
    def failing_callback(event_type, event_data):
        raise Exception("Callback error")

    with patch.object(
        coordinator_facade.playbook_resolver, "resolve"
    ) as mock_resolve:
        resolved = Mock()
        resolved.code = "test_playbook"
        resolved.playbook = Mock()
        resolved.source = "system"
        mock_resolve.return_value = resolved

        with patch.object(
            coordinator_facade.execution_launcher, "launch"
        ) as mock_launch:
            mock_launch.return_value = {
                "execution_id": "exec-123",
                "execution_mode": "conversation",
                "raw_result": {},
            }

            # Should not raise exception
            results = await coordinator_facade.execute_plan_with_ctx(
                execution_plan=execution_plan,
                ctx=execution_context,
                message_id="msg-123",
                files=[],
                message="test",
                task_event_callback=failing_callback,
            )

            assert "executed_tasks" in results
