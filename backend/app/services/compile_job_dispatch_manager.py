"""Compatibility shim for legacy compile-job background service wiring."""

from __future__ import annotations


class CompileJobDispatchManager:
    """No-op manager kept for legacy startup hooks."""

    def start_background_services(self) -> None:
        return

    def stop_background_services(self) -> None:
        return


_compile_job_dispatch_manager = CompileJobDispatchManager()


def get_compile_job_dispatch_manager() -> CompileJobDispatchManager:
    return _compile_job_dispatch_manager
