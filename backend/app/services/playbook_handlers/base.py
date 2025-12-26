"""
Playbook Handler Base Classes

Provides base classes and interfaces for playbook-specific handlers.
Playbooks can implement their own handlers in independent repositories.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)


class PlaybookHandler(ABC):
    """
    Base class for playbook-specific handlers

    Playbooks can implement this class in their independent repositories
    to provide custom API endpoints and business logic.
    """

    @abstractmethod
    def get_playbook_code(self) -> str:
        """
        Return the playbook code this handler serves

        Returns:
            str: Playbook code (e.g., 'yearly_personal_book')
        """
        pass

    @abstractmethod
    def register_routes(self, router: APIRouter) -> None:
        """
        Register playbook-specific routes

        This method is called by the handler registry to register
        custom routes for this playbook.

        Args:
            router: FastAPI router to register routes on
        """
        pass

    def get_handler_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about this handler

        Returns:
            Dict with handler information (version, description, etc.)
        """
        return {
            "playbook_code": self.get_playbook_code(),
            "version": "1.0.0"
        }


class PlaybookHandlerRegistry:
    """
    Registry for playbook handlers

    Handlers can be registered from:
    1. Core handlers (for built-in playbooks)
    2. NPM package handlers (from @mindscape/playbook-* packages)
    3. User-defined handlers (from workspace config)
    """

    def __init__(self):
        self.handlers: Dict[str, PlaybookHandler] = {}
        self._initialized = False

    def register(self, handler: PlaybookHandler) -> None:
        """
        Register a playbook handler

        Args:
            handler: PlaybookHandler instance
        """
        playbook_code = handler.get_playbook_code()

        if playbook_code in self.handlers:
            logger.warning(
                f"Handler for playbook {playbook_code} already registered. "
                f"Overwriting with new handler."
            )

        self.handlers[playbook_code] = handler
        logger.info(f"Registered handler for playbook: {playbook_code}")

    def get(self, playbook_code: str) -> Optional[PlaybookHandler]:
        """
        Get handler for a playbook

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookHandler instance or None if not found
        """
        return self.handlers.get(playbook_code)

    def has(self, playbook_code: str) -> bool:
        """
        Check if a handler is registered for a playbook

        Args:
            playbook_code: Playbook code

        Returns:
            True if handler exists, False otherwise
        """
        return playbook_code in self.handlers

    def list(self) -> List[str]:
        """
        List all registered playbook codes

        Returns:
            List of playbook codes with registered handlers
        """
        return list(self.handlers.keys())

    def register_all_routes(self, router: APIRouter) -> None:
        """
        Register all handler routes on the main router

        Args:
            router: Main FastAPI router
        """
        for playbook_code, handler in self.handlers.items():
            try:
                # Create a sub-router for this playbook
                playbook_router = APIRouter(
                    prefix=f"/api/v1/workspaces/{{workspace_id}}/playbooks/{playbook_code}",
                    tags=[f"playbook-{playbook_code}"]
                )

                # Let the handler register its routes
                handler.register_routes(playbook_router)

                # Include the sub-router in the main router
                router.include_router(playbook_router)

                logger.info(f"Registered routes for playbook: {playbook_code}")
            except Exception as e:
                logger.error(
                    f"Failed to register routes for playbook {playbook_code}: {e}",
                    exc_info=True
                )

    async def load_handlers_from_packages(self) -> None:
        """
        Dynamically load handlers from installed playbook packages

        Scans node_modules/@mindscape/playbook-* packages and loads
        handlers defined in their backend/handlers.py files.
        """
        if self._initialized:
            return

        try:
            from backend.app.services.playbook_loaders.npm_loader import PlaybookNpmLoader
            import importlib
            import sys
            from pathlib import Path

            packages = PlaybookNpmLoader.find_playbook_packages()

            for package in packages:
                playbook_code = package.get('playbook_code')
                package_name = package.get('name')

                if not playbook_code or not package_name:
                    continue

                try:
                    # Try to import handler from package
                    # Expected structure: @mindscape/playbook-xxx/backend/handlers.py
                    handler_module_path = f"{package_name.replace('@', '').replace('/', '.')}.backend.handlers"

                    # Alternative: try to load from package path
                    package_path = Path(f"node_modules/{package_name}")
                    if package_path.exists():
                        handler_file = package_path / "backend" / "handlers.py"
                        if handler_file.exists():
                            # Add package to Python path
                            if str(package_path) not in sys.path:
                                sys.path.insert(0, str(package_path))

                            # Import handler
                            try:
                                handler_module = importlib.import_module(
                                    f"{package_name.replace('@', '').replace('/', '.')}.backend.handlers"
                                )

                                # Look for handler class or register function
                                handler = None

                                # Try to find handler class
                                for attr_name in dir(handler_module):
                                    attr = getattr(handler_module, attr_name)
                                    if (isinstance(attr, type) and
                                        issubclass(attr, PlaybookHandler) and
                                        attr != PlaybookHandler):
                                        handler = attr()
                                        break

                                # Try to find register function
                                if not handler and hasattr(handler_module, 'register_handler'):
                                    handler = handler_module.register_handler()

                                if handler:
                                    self.register(handler)
                                    logger.info(
                                        f"Loaded handler from package: {package_name}"
                                    )
                            except ImportError as e:
                                logger.debug(
                                    f"Package {package_name} does not have a handler: {e}"
                                )
                except Exception as e:
                    logger.warning(
                        f"Failed to load handler from package {package_name}: {e}"
                    )

        except Exception as e:
            logger.error(f"Failed to load handlers from packages: {e}", exc_info=True)

        self._initialized = True


# Global registry instance
_handler_registry: Optional[PlaybookHandlerRegistry] = None


def get_handler_registry() -> PlaybookHandlerRegistry:
    """
    Get the global handler registry instance

    Returns:
        PlaybookHandlerRegistry singleton
    """
    global _handler_registry

    if _handler_registry is None:
        _handler_registry = PlaybookHandlerRegistry()

    return _handler_registry

