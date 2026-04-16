"""Compatibility shim for legacy compile-job task tracking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompileJobTaskRecord:
    job_id: str


class CompileJobTaskRegistry:
    def snapshot(self) -> list[CompileJobTaskRecord]:
        return []

    def cancel(self, job_id: str) -> None:
        return

    def unregister(self, job_id: str) -> None:
        return


compile_job_task_registry = CompileJobTaskRegistry()
