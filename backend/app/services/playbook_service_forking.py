from typing import Any, Optional

from backend.app.models.playbook import Playbook, PlaybookMetadata


async def fork_playbook_for_service(
    *,
    service: Any,
    source_playbook_code: str,
    target_playbook_code: str,
    workspace_id: str,
    profile_id: str,
    locale: str,
    logger: Any,
) -> Optional[Playbook]:
    """Fork a template playbook through the existing service facade."""
    try:
        source_playbook = await service.get_playbook(
            source_playbook_code,
            locale,
            workspace_id,
        )
        if not source_playbook:
            logger.error("Source playbook not found: %s", source_playbook_code)
            return None

        if not source_playbook.metadata.is_template():
            logger.warning(
                "Cannot fork non-template playbook: %s (scope: %s)",
                source_playbook_code,
                source_playbook.metadata.get_scope_level(),
            )
            return None

        new_metadata = PlaybookMetadata(
            playbook_code=target_playbook_code,
            version=source_playbook.metadata.version,
            locale=locale,
            name=f"{source_playbook.metadata.name} (Fork)",
            description=source_playbook.metadata.description,
            tags=source_playbook.metadata.tags.copy(),
            language_strategy=source_playbook.metadata.language_strategy,
            supports_execution_chat=source_playbook.metadata.supports_execution_chat,
            execution_chat_mode=source_playbook.metadata.execution_chat_mode,
            execution_chat_tool_groups=source_playbook.metadata.execution_chat_tool_groups.copy(),
            execution_chat_max_tool_iterations=source_playbook.metadata.execution_chat_max_tool_iterations,
            discussion_agent=source_playbook.metadata.discussion_agent,
            supported_locales=source_playbook.metadata.supported_locales.copy(),
            default_locale=source_playbook.metadata.default_locale,
            auto_localize=source_playbook.metadata.auto_localize,
            entry_agent_type=source_playbook.metadata.entry_agent_type,
            onboarding_task=source_playbook.metadata.onboarding_task,
            icon=source_playbook.metadata.icon,
            required_tools=source_playbook.metadata.required_tools.copy(),
            tool_dependencies=source_playbook.metadata.tool_dependencies.copy(),
            background=source_playbook.metadata.background,
            optional_tools=source_playbook.metadata.optional_tools.copy(),
            kind=source_playbook.metadata.kind,
            interaction_mode=source_playbook.metadata.interaction_mode.copy(),
            visible_in=source_playbook.metadata.visible_in.copy(),
            scope={"visibility": "workspace", "editable": True},
            owner={
                "type": "workspace",
                "workspace_id": workspace_id,
                "profile_id": profile_id,
            },
            runtime_handler=source_playbook.metadata.runtime_handler,
            runtime_tier=source_playbook.metadata.runtime_tier,
            runtime=source_playbook.metadata.runtime,
            x_platform=(
                source_playbook.metadata.x_platform.copy()
                if isinstance(source_playbook.metadata.x_platform, dict)
                else source_playbook.metadata.x_platform
            ),
        )
        forked_playbook = Playbook(
            metadata=new_metadata,
            sop_content=source_playbook.sop_content,
            user_notes=f"Forked from {source_playbook_code}",
        )

        if service.store:
            from backend.app.services.playbook_loaders.database_loader import (
                PlaybookDatabaseLoader,
            )

            _ = PlaybookDatabaseLoader
            logger.info(
                "Forked playbook %s -> %s for workspace %s",
                source_playbook_code,
                target_playbook_code,
                workspace_id,
            )

        service.registry.invalidate_cache(target_playbook_code, locale)
        return forked_playbook
    except Exception as exc:
        logger.error(
            "Failed to fork playbook %s: %s",
            source_playbook_code,
            exc,
            exc_info=True,
        )
        return None
