"""
Unit tests for PlaybookResolver module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from backend.app.services.conversation.playbook_resolver import (
    PlaybookResolver,
    ResolvedPlaybook,
)
from backend.app.mindscape.shims.execution_context import ExecutionContext


@pytest.fixture
def mock_playbook_service():
    """Create mock PlaybookService"""
    service = Mock()
    service.get_playbook = AsyncMock(return_value=None)
    return service


@pytest.fixture
def playbook_resolver(mock_playbook_service):
    """Create PlaybookResolver instance"""
    return PlaybookResolver(
        default_locale="en", playbook_service=mock_playbook_service
    )


@pytest.fixture
def execution_context():
    """Create sample ExecutionContext"""
    return ExecutionContext(
        actor_id="user-123",
        metadata={"workspace_id": "workspace-123", "tags": {"mode": "local"}},
    )


@pytest.mark.asyncio
async def test_resolve_capability_playbook(playbook_resolver, execution_context):
    """Test resolve from capability playbooks"""
    mock_playbook = Mock()
    mock_playbook.code = "capability_playbook"

    with patch("backend.app.services.capability_registry.get_registry") as mock_registry:
        registry = Mock()
        capability = Mock()
        registry.get_capability.return_value = capability
        registry.get_capability_playbooks.return_value = ["playbook.yaml"]
        mock_registry.return_value = registry

        playbook_resolver.playbook_service.get_playbook = AsyncMock(
            return_value=mock_playbook
        )

        resolved = await playbook_resolver.resolve("test_pack", ctx=execution_context)

        assert resolved is not None
        assert isinstance(resolved, ResolvedPlaybook)
        assert resolved.source == "capability"


@pytest.mark.asyncio
async def test_resolve_system_playbook(playbook_resolver, execution_context):
    """Test resolve from system playbooks"""
    mock_playbook = Mock()

    with patch("backend.app.services.capability_registry.get_registry") as mock_registry:
        registry = Mock()
        registry.get_capability.return_value = None
        mock_registry.return_value = registry

        playbook_resolver.playbook_service.get_playbook = AsyncMock(
            return_value=mock_playbook
        )

        resolved = await playbook_resolver.resolve("system_playbook", ctx=execution_context)

        assert resolved is not None
        assert isinstance(resolved, ResolvedPlaybook)
        assert resolved.source == "system"
        assert resolved.code == "system_playbook"


@pytest.mark.asyncio
async def test_resolve_not_found(playbook_resolver, execution_context):
    """Test resolve when playbook not found"""
    with patch("backend.app.services.capability_registry.get_registry") as mock_registry:
        registry = Mock()
        registry.get_capability.return_value = None
        mock_registry.return_value = registry

        playbook_resolver.playbook_service.get_playbook = AsyncMock(return_value=None)

        resolved = await playbook_resolver.resolve("unknown_pack", ctx=execution_context)

        assert resolved is None


@pytest.mark.asyncio
async def test_resolve_without_playbook_service(execution_context):
    """Test resolve without PlaybookService (should use registry)"""
    resolver = PlaybookResolver(default_locale="en", playbook_service=None)

    with patch("backend.app.services.capability_registry.get_registry") as mock_registry:
        registry = Mock()
        registry.get_capability.return_value = None
        mock_registry.return_value = registry

        # Without PlaybookService, resolve should return None
        resolved = await resolver.resolve("system_playbook", ctx=execution_context)

        # Since PlaybookLoader is removed, this should return None
        assert resolved is None


@pytest.mark.asyncio
async def test_get_playbook_with_service(playbook_resolver, execution_context):
    """Test get_playbook using PlaybookService"""
    mock_playbook = Mock()
    playbook_resolver.playbook_service.get_playbook = AsyncMock(
        return_value=mock_playbook
    )

    result = await playbook_resolver.get_playbook("test_playbook", ctx=execution_context)

    assert result == mock_playbook
    playbook_resolver.playbook_service.get_playbook.assert_called_once_with(
        "test_playbook", locale="en", workspace_id="workspace-123"
    )


@pytest.mark.asyncio
async def test_get_playbook_without_service(execution_context):
    """Test get_playbook without PlaybookService"""
    resolver = PlaybookResolver(default_locale="en", playbook_service=None)

    # Without PlaybookService, get_playbook should return None
    # (PlaybookLoader has been removed)
    result = await resolver.get_playbook("test_playbook", ctx=execution_context)

    assert result is None


@pytest.mark.asyncio
async def test_get_playbook_exception(playbook_resolver, execution_context):
    """Test get_playbook when exception occurs"""
    playbook_resolver.playbook_service.get_playbook = AsyncMock(
        side_effect=Exception("Load error")
    )

    result = await playbook_resolver.get_playbook("test_playbook", ctx=execution_context)

    assert result is None
