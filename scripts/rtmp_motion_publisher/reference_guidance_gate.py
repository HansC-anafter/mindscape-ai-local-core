from __future__ import annotations

from dataclasses import dataclass


CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS = 3


@dataclass(frozen=True)
class ReferenceGuidanceGateState:
    ready: bool
    committed_chapter_id: str | None
    pending_chapter_id: str | None
    pending_count: int


class ReferenceGuidanceGate:
    """Promote chapter identity to guidance only after stable live evidence."""

    def __init__(self) -> None:
        self.committed_chapter_id: str | None = None
        self.pending_chapter_id: str | None = None
        self.pending_count = 0

    def observe(
        self,
        chapter_id: str,
        *,
        localization_ready: bool,
    ) -> ReferenceGuidanceGateState:
        if not localization_ready:
            self._reset_pending()
            return self._state(ready=False)

        if self.committed_chapter_id is None:
            self.committed_chapter_id = chapter_id
            self._reset_pending()
            return self._state(ready=True)

        if chapter_id == self.committed_chapter_id:
            self._reset_pending()
            return self._state(ready=True)

        if chapter_id == self.pending_chapter_id:
            self.pending_count += 1
        else:
            self.pending_chapter_id = chapter_id
            self.pending_count = 1

        if self.pending_count < CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS:
            return self._state(ready=False)

        self.committed_chapter_id = chapter_id
        self._reset_pending()
        return self._state(ready=True)

    def _reset_pending(self) -> None:
        self.pending_chapter_id = None
        self.pending_count = 0

    def _state(self, *, ready: bool) -> ReferenceGuidanceGateState:
        return ReferenceGuidanceGateState(
            ready=ready,
            committed_chapter_id=self.committed_chapter_id,
            pending_chapter_id=self.pending_chapter_id,
            pending_count=self.pending_count,
        )


__all__ = [
    "CHAPTER_GUIDANCE_CONFIRMATION_WINDOWS",
    "ReferenceGuidanceGate",
    "ReferenceGuidanceGateState",
]
