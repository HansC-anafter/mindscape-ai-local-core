"""Own one isolated tracefs instance and one kernel-side signal filter."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TextIO


SIGNAL_FILTER = 'sig == 3 && comm == "postgres"'
INSTANCE_NAME = "mindscape_postgres_sigquit"


class TraceFsInstance:
    """Minimal tracefs control writer; never touches the global trace buffer."""

    def __init__(
        self,
        trace_root: Path = Path("/sys/kernel/tracing"),
        *,
        instance_name: str = INSTANCE_NAME,
    ) -> None:
        self.trace_root = Path(trace_root)
        self.instance_name = instance_name
        self.instance_root = self.trace_root / "instances" / instance_name
        self.event_root = self.instance_root / "events" / "signal" / "signal_generate"
        self.mounted_by_observer = False

    def _ensure_tracefs(self) -> None:
        global_event = self.trace_root / "events" / "signal" / "signal_generate"
        if global_event.is_dir():
            return
        self.trace_root.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["mount", "-t", "tracefs", "tracefs", str(self.trace_root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if completed.returncode != 0 or not global_event.is_dir():
            raise RuntimeError("tracefs_mount_or_signal_event_unavailable")
        self.mounted_by_observer = True

    @staticmethod
    def _write(path: Path, value: str) -> None:
        try:
            path.write_text(value, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"tracefs_control_write_failed:{path.name}") from exc

    def prepare(self) -> str:
        self._ensure_tracefs()
        self.instance_root.mkdir(parents=True, exist_ok=True)
        self._write(self.instance_root / "tracing_on", "0")
        self._write(self.event_root / "enable", "0")
        self._write(self.event_root / "filter", SIGNAL_FILTER)
        actual_filter = (
            (self.event_root / "filter")
            .read_text(encoding="utf-8", errors="replace")
            .strip()
        )
        if "sig == 3" not in actual_filter or 'comm == "postgres"' not in actual_filter:
            raise RuntimeError("tracefs_filter_readback_mismatch")
        self._write(self.instance_root / "trace", "")
        self._write(self.event_root / "enable", "1")
        self._write(self.instance_root / "tracing_on", "1")
        return actual_filter

    def open_pipe(self) -> TextIO:
        try:
            return (self.instance_root / "trace_pipe").open(
                "r", encoding="utf-8", errors="replace", buffering=1
            )
        except OSError as exc:
            raise RuntimeError("tracefs_trace_pipe_unavailable") from exc

    def cleanup(self) -> None:
        if self.instance_root.exists():
            for path, value in (
                (self.instance_root / "tracing_on", "0"),
                (self.event_root / "enable", "0"),
            ):
                if path.exists():
                    try:
                        path.write_text(value, encoding="utf-8")
                    except OSError:
                        pass
            try:
                self.instance_root.rmdir()
            except OSError:
                pass
        if self.mounted_by_observer:
            subprocess.run(
                ["umount", str(self.trace_root)],
                check=False,
                capture_output=True,
                timeout=5,
            )
            self.mounted_by_observer = False
