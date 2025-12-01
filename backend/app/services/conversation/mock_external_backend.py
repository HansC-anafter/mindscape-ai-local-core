"""
Mock External Backend for Testing

Provides mock implementations of ExternalBackend for testing purposes.
Used when other clusters (Semantic-Hub, Site-Hub, CRS-Hub) are not yet implemented.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from .external_backend import ExternalBackend

logger = logging.getLogger(__name__)


class MockExternalBackend(ExternalBackend):
    """
    Mock ExternalBackend for testing

    Simulates ExternalBackend behavior for testing without requiring actual cluster implementation.
    """

    def __init__(
        self,
        simulate_success: bool = True,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
        return_session_source: bool = False,
        delay_seconds: float = 0.1
    ):
        """
        Initialize mock backend

        Args:
            simulate_success: Whether to simulate successful retrieval
            simulate_timeout: Whether to simulate timeout error
            simulate_error: Whether to simulate general error
            return_session_source: Whether to return session source (for boundary testing)
            delay_seconds: Simulated delay in seconds
        """
        self.simulate_success = simulate_success
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.return_session_source = return_session_source
        self.delay_seconds = delay_seconds

        self.call_count = 0
        self.last_request: Optional[Dict[str, Any]] = None

    async def retrieve_context(
        self,
        workspace_id: str,
        message: str,
        workspace_context: Dict[str, Any],
        profile_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Mock context retrieval

        Simulates ExternalBackend.retrieve_context() behavior for testing.
        """
        self.call_count += 1
        self.last_request = {
            "workspace_id": workspace_id,
            "message": message,
            "workspace_context": workspace_context,
            "profile_id": profile_id,
            "session_id": session_id
        }

        # Simulate delay
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        # Simulate timeout
        if self.simulate_timeout:
            raise asyncio.TimeoutError("Mock timeout simulation")

        # Simulate error
        if self.simulate_error:
            return {
                "success": False,
                "retrieved_context": "",
                "retrieved_snippets": [],
                "retrieval_metadata": {"error": "Mock error simulation"}
            }

        # Simulate success
        if self.simulate_success:
            snippets = [
                {
                    "content": f"Mock retrieved content 1 for query: {message[:50]}",
                    "relevance_score": 0.85,
                    "source": "semantic",
                    "metadata": {"mock": True}
                },
                {
                    "content": f"Mock retrieved content 2 for query: {message[:50]}",
                    "relevance_score": 0.75,
                    "source": "knowledge_base",
                    "metadata": {"mock": True}
                }
            ]

            # Add session source if requested (for boundary testing)
            if self.return_session_source:
                snippets.append({
                    "content": "Mock session content (should be filtered)",
                    "relevance_score": 0.80,
                    "source": "session",
                    "metadata": {"mock": True}
                })

            return {
                "success": True,
                "retrieved_context": "\n".join([s["content"] for s in snippets]),
                "retrieved_snippets": snippets,
                "retrieval_metadata": {
                    "iterations": 1,
                    "confidence_score": 0.80,
                    "query_variations": [message],
                    "total_results": len(snippets)
                }
            }

        # Default: return empty result
        return {
            "success": False,
            "retrieved_context": "",
            "retrieved_snippets": [],
            "retrieval_metadata": {}
        }

    async def list_capabilities(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """Mock capabilities list"""
        return {
            "success": True,
            "capabilities": [
                {
                    "capability_key": "mock_capability",
                    "name": "Mock Capability",
                    "description": "Mock capability for testing",
                    "category": "test",
                    "parameters": {},
                    "available": True
                }
            ]
        }

    async def sync_artifact(
        self,
        workspace_id: str,
        artifact: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mock artifact sync"""
        return {
            "success": True,
            "artifact_id": artifact.get("artifact_id", "mock_artifact_id"),
            "synced_at": "2025-11-29T00:00:00Z"
        }


def create_backend(options: Dict[str, Any]) -> ExternalBackend:
    """
    Create Mock backend instance for testing

    Args:
        options: {
            "simulate_success": bool,      # Default: True
            "simulate_timeout": bool,      # Default: False
            "simulate_error": bool,        # Default: False
            "return_session_source": bool, # Default: False
            "delay_seconds": float         # Default: 0.1
        }

    Returns:
        MockExternalBackend instance
    """
    return MockExternalBackend(
        simulate_success=options.get("simulate_success", True),
        simulate_timeout=options.get("simulate_timeout", False),
        simulate_error=options.get("simulate_error", False),
        return_session_source=options.get("return_session_source", False),
        delay_seconds=options.get("delay_seconds", 0.1)
    )
