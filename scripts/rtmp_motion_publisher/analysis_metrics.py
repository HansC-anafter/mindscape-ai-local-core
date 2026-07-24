from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable


@dataclass
class _StageTiming:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def record(self, elapsed_ms: float) -> None:
        value = max(0.0, float(elapsed_ms))
        self.count += 1
        self.total_ms += value
        self.max_ms = max(self.max_ms, value)

    def snapshot(self) -> dict[str, int | float]:
        mean_ms = self.total_ms / self.count if self.count else 0.0
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 3),
            "mean_ms": round(mean_ms, 3),
            "max_ms": round(self.max_ms, 3),
        }


@dataclass
class AnalysisStageMetrics:
    """Bounded host diagnostics for the synchronous receiver analysis path."""

    clock: Callable[[], float]
    _stages: dict[str, _StageTiming] = field(default_factory=dict)
    _sample_schedule_lag: _StageTiming = field(default_factory=_StageTiming)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def started(self) -> float:
        return self.clock()

    def record(self, stage: str, started_at: float) -> None:
        elapsed_ms = (self.clock() - started_at) * 1000.0
        with self._lock:
            self._stages.setdefault(stage, _StageTiming()).record(elapsed_ms)

    def record_sample_schedule_lag(
        self,
        *,
        sampled_at: float,
        scheduled_at: float,
    ) -> None:
        with self._lock:
            self._sample_schedule_lag.record((sampled_at - scheduled_at) * 1000.0)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "stages": {
                    stage: timing.snapshot()
                    for stage, timing in sorted(self._stages.items())
                },
                "sample_schedule_lag": self._sample_schedule_lag.snapshot(),
            }
