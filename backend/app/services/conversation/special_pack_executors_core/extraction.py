"""Seed extraction helpers for special pack executors."""

import logging
from typing import List

logger = logging.getLogger(__name__)


async def extract_intents_from_files(
    *,
    config_store,
    profile_id: str,
    message_id: str,
    message: str,
    file_contents: List[str],
) -> List[str]:
    try:
        llm_provider = _get_llm_provider(config_store, profile_id)
        if llm_provider:
            extractor = _build_seed_extractor(llm_provider)
            combined_content = "\n\n".join(file_contents[:3])
            seeds = await extractor.extract_seeds_from_content(
                user_id=profile_id,
                content=combined_content,
                source_type="conversation",
                source_id=message_id,
                source_context=message,
            )
            return _intent_seed_texts(seeds)
    except Exception as exc:
        logger.warning(
            "SpecialPackExecutors: Failed to extract seeds from files: %s",
            exc,
        )

    return []


async def extract_intents_from_message(
    *,
    config_store,
    profile_id: str,
    message_id: str,
    message: str,
) -> List[str]:
    try:
        llm_provider = _get_llm_provider(config_store, profile_id)
        if llm_provider:
            extractor = _build_seed_extractor(llm_provider)
            seeds = await extractor.extract_seeds_from_content(
                user_id=profile_id,
                content=message,
                source_type="conversation",
                source_id=message_id,
                source_context=message,
            )
            extracted_intents = _intent_seed_texts(seeds)
            logger.info(
                "SpecialPackExecutors: Extracted %s intents from message content",
                len(extracted_intents),
            )
            return extracted_intents
    except Exception as exc:
        logger.warning(
            "SpecialPackExecutors: Failed to extract seeds from message: %s",
            exc,
            exc_info=True,
        )

    return []


def _get_llm_provider(config_store, profile_id: str):
    from backend.app.shared.llm_provider_helper import (
        create_llm_provider_manager,
        get_llm_provider_from_settings,
    )

    config = config_store.get_or_create_config(profile_id)
    llm_manager = create_llm_provider_manager(
        openai_key=config.agent_backend.openai_api_key,
        anthropic_key=config.agent_backend.anthropic_api_key,
        vertex_api_key=config.agent_backend.vertex_api_key,
        vertex_project_id=config.agent_backend.vertex_project_id,
        vertex_location=config.agent_backend.vertex_location,
    )
    return get_llm_provider_from_settings(llm_manager)


def _build_seed_extractor(llm_provider):
    from backend.app.capabilities.semantic_seeds.services.seed_extractor import (
        SeedExtractor,
    )

    return SeedExtractor(llm_provider=llm_provider)


def _intent_seed_texts(seeds) -> List[str]:
    return [
        seed.get("text", "")
        for seed in seeds
        if seed.get("type") in ["intent", "project"]
    ]
