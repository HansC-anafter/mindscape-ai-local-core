"""Intent steward signal filtering helpers."""

import logging
from typing import List, Optional

from backend.app.models.mindscape import IntentCard, IntentSignal

logger = logging.getLogger(__name__)


async def prefilter_signals(service, signals: List[IntentSignal]) -> List[IntentSignal]:
    if not signals:
        return []

    high_confidence = [
        signal
        for signal in signals
        if signal.confidence and signal.confidence >= service.MIN_CONFIDENCE_THRESHOLD
    ]
    if not high_confidence:
        return []

    seen_labels = {}
    deduped = []
    for signal in high_confidence:
        label_key = signal.label.strip().lower()
        if label_key not in seen_labels:
            seen_labels[label_key] = True
            deduped.append(signal)

    filtered = []
    for signal in deduped:
        label = signal.label.strip()
        label_clean = label.replace(" ", "").replace("\n", "")
        if 3 <= len(label) <= 200 and not label_clean.isdigit() and label_clean:
            filtered.append(signal)
            if len(filtered) >= service.MAX_PREFILTERED_SIGNALS:
                break

    logger.info(
        f"IntentSteward: Prefiltered {len(signals)} signals -> {len(filtered)} candidates"
    )
    return filtered


def find_similar_intent(
    label: str, existing_intents: List[IntentCard]
) -> Optional[IntentCard]:
    label_lower = label.lower().strip()
    for intent in existing_intents:
        title = intent.title.lower().strip()
        if title == label_lower:
            return intent
        if title[:20] == label_lower[:20]:
            return intent
    return None
