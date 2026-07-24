from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from rtmp_motion_publisher.jpeg_pipe import BoundedJpegFrameParser


PIPE_READ_SIZE = 64 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024


class SequentialFfmpegFrameCapture:
    """Decode every filtered frame in order for offline profile analysis."""

    def __init__(
        self,
        path: str | Path,
        *,
        ffmpeg_bin: str,
        sample_fps: float,
        frame_width: int,
        frame_height: int,
    ) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.parser = BoundedJpegFrameParser(max_frame_bytes=MAX_FRAME_BYTES)
        self.process = subprocess.Popen(
            [
                ffmpeg_bin,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-an",
                "-vf",
                f"fps={max(0.1, sample_fps)},scale={frame_width}:{frame_height}",
                "-c:v",
                "mjpeg",
                "-q:v",
                "4",
                "-f",
                "image2pipe",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def is_opened(self) -> bool:
        return self.process.stdout is not None

    def read(self) -> tuple[bool, Any]:
        if self.process.stdout is None:
            return False, None
        while True:
            payload = self.parser.pop_frame()
            if payload is not None:
                frame = cv2.imdecode(
                    np.frombuffer(payload, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is not None and frame.shape[:2] == (
                    self.frame_height,
                    self.frame_width,
                ):
                    return True, frame
                continue
            chunk = os.read(self.process.stdout.fileno(), PIPE_READ_SIZE)
            if not chunk:
                return False, None
            self.parser.feed(chunk)

    def release(self) -> None:
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)


__all__ = ["SequentialFfmpegFrameCapture"]

