"""
External Backend Protocol Interface

Defines the protocol interface for external backend services.
Mindscape core only recognizes this protocol and does not know specific implementations.

Key Principles:
- Mindscape core only knows this protocol, not specific implementations
- All external services (cloud backends, custom tools) implement this protocol as plugins
- Core has no hardcoding of specific backend implementations
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ExternalBackend(ABC):
    """
    External Backend Protocol Interface

    All external backend services must implement this protocol.
    Mindscape core only knows this interface, not specific implementations.
    """

    @abstractmethod
    async def retrieve_context(
        self,
        workspace_id: str,
        message: str,
        workspace_context: Dict[str, Any],
        profile_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve context from external backend (RAG-only)

        This method should:
        - Receive Mindscape's workspace context
        - Transform to standardized format (if needed)
        - Call downstream services for RAG retrieval
        - Return RAG-only results (no workspace/intents/tasks duplication)

        Args:
            workspace_id: Workspace identifier
            message: User query text
            workspace_context: Workspace context from Mindscape (workspace metadata, intents, tasks, etc.)
            profile_id: User profile identifier
            session_id: Session identifier

        Returns:
            {
                "success": bool,
                "retrieved_context": str,  # RAG-only context text
                "retrieved_snippets": [
                    {
                        "content": str,
                        "relevance_score": float,
                        "source": str,  # "semantic" | "knowledge_base" | "global"
                        "metadata": Dict[str, Any]
                    }
                ],
                "retrieval_metadata": {
                    "iterations": int,
                    "confidence_score": float,
                    "query_variations": List[str],
                    "total_results": int
                }
            }
        """
        pass

    @abstractmethod
    async def list_capabilities(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        List available capabilities (optional)

        Returns available external capabilities (e.g., CRS / MCP pack list).

        Args:
            workspace_id: Workspace identifier

        Returns:
            {
                "success": bool,
                "capabilities": [
                    {
                        "capability_key": str,
                        "name": str,
                        "description": str,
                        "category": str,
                        "parameters": Dict[str, Any],
                        "available": bool
                    }
                ]
            }
        """
        pass

    @abstractmethod
    async def sync_artifact(
        self,
        workspace_id: str,
        artifact: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Sync workspace artifact to cloud (optional)

        Sync workspace artifacts (e.g., files, outlines, INSIGHT summary) to cloud.

        Args:
            workspace_id: Workspace identifier
            artifact: Artifact data
                {
                    "artifact_id": str,
                    "artifact_type": str,  # "file" | "document" | "output" | "insight"
                    "artifact_name": str,
                    "content": str,
                    "metadata": Dict[str, Any]
                }

        Returns:
            {
                "success": bool,
                "artifact_id": str,
                "synced_at": str  # ISO timestamp
            }
        """
        pass


def validate_mindscape_boundary(
    client_kind: str,
    memory_policy: Dict[str, Any],
    request_metadata: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validate Mindscape boundary rules

    Ensures that cloud services do not violate memory boundaries.

    Args:
        client_kind: Client type identifier (e.g., "mindscape_edge", "cloud_mindspace")
        memory_policy: Memory policy configuration
        request_metadata: Request metadata

    Returns:
        (is_valid, violations): Whether validation passed, list of violations

    Rules:
    1. Mindscape route: memory_mode must be "external" (not allowed to override)
    2. No conversation history should be read from log tables
    3. No session source results for Mindscape route
    """
    violations = []

    # Check 1: memory_mode source
    if client_kind in ["mindscape_edge", "cloud_mindspace"]:
        if memory_policy.get("allow_chat_history_write", False):
            violations.append("Mindscape route does not allow allow_chat_history_write=True")

        # Check for frontend override attempts
        if request_metadata.get("memory_policy_override"):
            violations.append("Detected frontend attempt to override memory_policy (ignored)")

    # Check 2: Check for log table reading
    if request_metadata.get("conversation_history_source") == "log_table":
        violations.append("Detected reading conversation_history from log table (forbidden)")

    return len(violations) == 0, violations


def filter_mindscape_results(
    results: List[Dict[str, Any]],
    client_kind: str
) -> List[Dict[str, Any]]:
    """
    Filter Mindscape route retrieval results (remove session source)

    Hard rule: Mindscape route does not allow session source results.

    Args:
        results: List of retrieval results
        client_kind: Client type identifier

    Returns:
        Filtered results (session source removed for Mindscape routes)
    """
    if client_kind not in ["mindscape_edge", "cloud_mindspace"]:
        return results

    # Hard rule: Remove all session source results
    filtered = [
        r for r in results
        if r.get("source") != "session"
    ]

    if len(filtered) < len(results):
        logger.warning(
            f"Filtered out {len(results) - len(filtered)} session source results "
            f"(Mindscape route does not allow session source)"
        )

    return filtered


async def load_external_backend(config: Dict[str, Any]) -> Optional[ExternalBackend]:
    """
    Dynamically load external backend (protocol-driven)

    Core does not know what implementation driver corresponds to.
    Only responsible for dynamically loading the corresponding package and calling create_backend().

    Args:
        config: {
            "driver": str,      # e.g., "external.backend" or "@external/mindscape-backend"
            "options": Dict     # Backend configuration options
        }

    Returns:
        ExternalBackend instance, or None (if loading failed)

    Note:
    - Core completely does not know what driver corresponds to
    - Only responsible for dynamically loading the corresponding package and calling create_backend()
    """
    import importlib

    driver = config.get("driver")
    options = config.get("options", {})

    if not driver:
        return None

    try:
        # Dynamically load plugin package
        # Try multiple import strategies with fallback options for different backend types

        module = None

        # Strategy 1: Relative import (starts with ".")
        if driver.startswith("."):
            # Use current module's package for relative imports
            current_package = __name__.rsplit(".", 1)[0]  # Get package name
            module = importlib.import_module(driver, package=current_package)
        # Strategy 2: Built-in backend shortcuts
        elif driver in ["mock_external_backend"]:
            # Use current module's package for relative imports
            current_package = __name__.rsplit(".", 1)[0]  # Get package name
            module = importlib.import_module(f".{driver}", package=current_package)
        # Strategy 3: Absolute import (external package)
        else:
            try:
                module = importlib.import_module(driver)
            except ImportError:
                # Fallback: try as relative import
                try:
                    current_package = __name__.rsplit(".", 1)[0]  # Get package name
                    module = importlib.import_module(f".{driver}", package=current_package)
                except ImportError:
                    raise ImportError(f"Cannot import backend driver: {driver}")

        # Call plugin's create_backend() function
        # Plugin must implement: def create_backend(options: Dict) -> ExternalBackend
        create_backend = getattr(module, "create_backend")
        backend = create_backend(options)

        # Validate returned instance conforms to protocol
        if not isinstance(backend, ExternalBackend):
            logger.error(f"Plugin {driver} returned instance does not conform to ExternalBackend protocol")
            return None

        logger.info(f"✅ Successfully loaded external backend: {driver}")
        return backend

    except ImportError as e:
        logger.warning(f"⚠️ Cannot load plugin package {driver}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Failed to load external backend: {e}")
        return None
