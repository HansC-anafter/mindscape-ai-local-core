"""Label generation for intent clusters."""

import logging
from typing import List

from backend.app.models.mindscape import IntentCard

logger = logging.getLogger(__name__)


def load_llm_helpers():
    """Load LLM helpers lazily."""
    from backend.app.shared.llm_provider_helper import (
        create_llm_provider_manager,
        get_model_name_from_chat_model,
    )
    from backend.app.shared.llm_utils import build_prompt, call_llm

    return (
        call_llm,
        build_prompt,
        create_llm_provider_manager,
        get_model_name_from_chat_model,
    )


async def generate_cluster_label(cluster_intent_cards: List[IntentCard]) -> str:
    """Generate a cluster label using the configured LLM."""
    try:
        if not cluster_intent_cards:
            return "Unnamed Cluster"

        titles = [intent.title for intent in cluster_intent_cards[:10]]
        titles_text = "\n".join([f"- {title}" for title in titles])

        prompt = (
            "Based on the following IntentCard titles, generate a concise "
            "cluster label (2-4 words) that represents the common theme:\n\n"
            f"{titles_text}\n\n"
            "Cluster label (2-4 words, in English, no quotes):"
        )

        (
            call_llm,
            build_prompt,
            create_llm_provider_manager,
            get_model_name_from_chat_model,
        ) = load_llm_helpers()

        model_name = get_model_name_from_chat_model()
        if not model_name:
            return cluster_intent_cards[0].title[:30]

        try:
            response = await call_llm(
                messages=build_prompt(user_prompt=prompt),
                llm_provider=create_llm_provider_manager(),
                model=model_name,
                temperature=0.3,
                max_tokens=20,
                purpose="intent_cluster_label_generation",
                stage_name="scope_decision",
                risk_level="read",
            )

            label = response.get("text", "").strip().strip('"').strip("'")
            if len(label) > 50:
                label = label[:50]

            return label if label else cluster_intent_cards[0].title[:30]
        except Exception as exc:
            logger.warning("Failed to generate cluster label with LLM: %s", exc)
            return cluster_intent_cards[0].title[:30]

    except Exception as exc:
        logger.error("Failed to generate cluster label: %s", exc, exc_info=True)
        return cluster_intent_cards[0].title[:30] if cluster_intent_cards else "Unnamed Cluster"
