"""
Playbook Resolver

Resolves playbook code from pack_id/capability and loads playbook instance.
Uses PlaybookService as the only source. Returns None if PlaybookService is not available.
"""

import logging
from typing import Optional, Any
from dataclasses import dataclass

from ...core.domain_context import LocalDomainContext

logger = logging.getLogger(__name__)


@dataclass
class ResolvedPlaybook:
    """
    Resolved playbook data structure

    Contains playbook code, instance, and source information.
    """

    code: str
    playbook: Any
    source: str  # "capability" or "system"


class PlaybookResolver:
    """
    Resolves playbook code and loads playbook instance

    Responsibilities:
    - Determine playbook_code from pack_id/capability
    - Load playbook from capability packs or system playbooks
    - Support both PlaybookService and PlaybookLoader
    - Handle playbook resolution errors
    """

    def __init__(
        self,
        default_locale: str = "en",
        playbook_service=None,
    ):
        """
        Initialize PlaybookResolver

        Args:
            default_locale: Default locale for i18n
            playbook_service: Optional PlaybookService instance (for unified query)
        """
        self.default_locale = default_locale
        self.playbook_service = playbook_service

    async def resolve(
        self,
        pack_id: str,
        ctx: Optional[LocalDomainContext] = None,
    ) -> Optional[ResolvedPlaybook]:
        """
        Resolve playbook code from pack_id

        Args:
            pack_id: Pack identifier
            ctx: Optional execution context

        Returns:
            ResolvedPlaybook if found, None otherwise
        """
        # Try capability playbooks first
        resolved = await self._try_capability_playbooks(pack_id, ctx)

        if resolved:
            return resolved

        # Fallback to system playbooks
        resolved = await self._try_system_playbooks(pack_id, ctx)

        return resolved

    async def _try_capability_playbooks(
        self, pack_id: str, ctx: Optional[LocalDomainContext]
    ) -> Optional[ResolvedPlaybook]:
        """
        Try to resolve playbook from capability packs

        Args:
            pack_id: Pack identifier
            ctx: Optional execution context

        Returns:
            ResolvedPlaybook if found, None otherwise
        """
        try:
            from ...capabilities.registry import get_registry

            registry = get_registry()
            capability = registry.get_capability(pack_id)
            capability_playbooks = (
                registry.get_capability_playbooks(pack_id) if capability else []
            )

            if not capability or not capability_playbooks:
                return None

            playbook_codes_to_try = []
            for playbook_filename in capability_playbooks:
                base_name = playbook_filename.replace(".yaml", "").replace(".yml", "")
                if base_name not in playbook_codes_to_try:
                    playbook_codes_to_try.append(base_name)

            workspace_id = ctx.workspace_id if ctx else None

            for code in playbook_codes_to_try:
                try:
                    if self.playbook_service:
                        playbook = await self.playbook_service.get_playbook(
                            code,
                            locale=self.default_locale,
                            workspace_id=workspace_id,
                        )
                    else:
                        # PlaybookLoader has been removed, skip if no PlaybookService
                        continue

                    if playbook:
                        logger.info(
                            f"Resolved playbook {code} for capability pack {pack_id}"
                        )
                        return ResolvedPlaybook(
                            code=code, playbook=playbook, source="capability"
                        )
                except Exception:
                    continue

            return None

        except Exception as e:
            logger.warning(
                f"Failed to resolve capability playbooks for {pack_id}: {e}"
            )
            return None

    async def _try_system_playbooks(
        self, pack_id: str, ctx: Optional[LocalDomainContext]
    ) -> Optional[ResolvedPlaybook]:
        """
        Try to resolve playbook from system playbooks

        Args:
            pack_id: Pack identifier
            ctx: Optional execution context

        Returns:
            ResolvedPlaybook if found, None otherwise
        """
        try:
            workspace_id = ctx.workspace_id if ctx else None

            if self.playbook_service:
                playbook = await self.playbook_service.get_playbook(
                    pack_id,
                    locale=self.default_locale,
                    workspace_id=workspace_id,
                )
            else:
                # PlaybookLoader has been removed, return None if no PlaybookService
                return None

            if playbook:
                logger.info(f"Resolved system playbook {pack_id}")
                return ResolvedPlaybook(
                    code=pack_id, playbook=playbook, source="system"
                )

            return None

        except Exception as e:
            logger.debug(f"Failed to resolve system playbook for {pack_id}: {e}")
            return None

    async def get_playbook(
        self, playbook_code: str, ctx: Optional[LocalDomainContext] = None
    ):
        """
        Get playbook instance by code

        Args:
            playbook_code: Playbook code
            ctx: Optional execution context

        Returns:
            Playbook instance or None if not found
        """
        try:
            workspace_id = ctx.workspace_id if ctx else None

            if self.playbook_service:
                return await self.playbook_service.get_playbook(
                    playbook_code,
                    locale=self.default_locale,
                    workspace_id=workspace_id,
                )
            else:
                # PlaybookLoader has been removed, return None if no PlaybookService
                return None
        except Exception as e:
            logger.warning(f"Failed to load playbook {playbook_code}: {e}")
            return None
