from __future__ import annotations

import argparse
import os
import selectors
import subprocess
import time
from typing import Any

import cv2
import numpy as np

from .events import emit


class OpenCvStreamCapture:
    def __init__(self, rtmp_url: str, *, read_timeout_sec: float) -> None:
        self.capture = self._open(rtmp_url, read_timeout_sec=read_timeout_sec)

    @staticmethod
    def _open(rtmp_url: str, *, read_timeout_sec: float) -> Any:
        params: list[int] = []
        timeout_ms = max(1000, int(read_timeout_sec * 1000.0))
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            params.extend([int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), timeout_ms])
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            params.extend([int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), timeout_ms])
        try:
            if params and hasattr(cv2, "CAP_FFMPEG"):
                capture = cv2.VideoCapture(rtmp_url, cv2.CAP_FFMPEG, params)
            elif hasattr(cv2, "CAP_FFMPEG"):
                capture = cv2.VideoCapture(rtmp_url, cv2.CAP_FFMPEG)
            else:
                capture = cv2.VideoCapture(rtmp_url)
        except TypeError:
            capture = cv2.VideoCapture(rtmp_url)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    def isOpened(self) -> bool:
        return bool(self.capture.isOpened())

    def read(self) -> tuple[bool, Any]:
        return self.capture.read()

    def release(self) -> None:
        self.capture.release()


class FfmpegRawFrameCapture:
    def __init__(
        self,
        *,
        rtmp_url: str,
        ffmpeg_bin: str,
        sample_fps: float,
        frame_width: int,
        frame_height: int,
        read_timeout_sec: float,
        avfoundation_framerate: float,
        ffmpeg_realtime_input: bool,
    ) -> None:
        self.rtmp_url = rtmp_url
        self.ffmpeg_bin = ffmpeg_bin
        self.sample_fps = sample_fps
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.read_timeout_sec = read_timeout_sec
        self.avfoundation_framerate = avfoundation_framerate
        self.ffmpeg_realtime_input = ffmpeg_realtime_input
        self.frame_size = frame_width * frame_height * 3
        self.process: subprocess.Popen[bytes] | None = None
        self.selector: selectors.BaseSelector | None = None
        self._open()

    def _input_args(self) -> list[str]:
        if self.rtmp_url.startswith("avfoundation:"):
            source = self.rtmp_url.removeprefix("avfoundation:")
            return [
                "-f",
                "avfoundation",
                "-framerate",
                str(max(1.0, self.avfoundation_framerate)),
                "-i",
                source,
            ]
        if self.rtmp_url.startswith(("rtsp://", "rtsps://")):
            input_args = [
                "-rtsp_transport",
                "tcp",
                "-timeout",
                str(max(1_000_000, int(self.read_timeout_sec * 1_000_000))),
            ]
            if self.rtmp_url.startswith("rtsps://"):
                input_args.extend(["-tls_verify", "1"])
            return [*input_args, "-i", self.rtmp_url]
        return ["-i", self.rtmp_url]

    def _open(self) -> None:
        fps = max(0.1, self.sample_fps)
        cmd = [
            self.ffmpeg_bin,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            *(["-re"] if self.ffmpeg_realtime_input else []),
            *self._input_args(),
            "-an",
            "-vf",
            f"fps={fps},scale={self.frame_width}:{self.frame_height}",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            emit(
                {
                    "event": "ffmpeg_open_failed",
                    "ffmpeg_bin": self.ffmpeg_bin,
                    "error": str(exc),
                }
            )
            self.process = None
            return
        if self.process.stdout is not None:
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def isOpened(self) -> bool:
        return (
            self.process is not None
            and self.process.stdout is not None
            and self.selector is not None
            and self.process.poll() is None
        )

    def read(self) -> tuple[bool, Any]:
        if not self.isOpened() or self.process is None or self.process.stdout is None:
            return False, None
        chunks: list[bytes] = []
        remaining = self.frame_size
        deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
        fd = self.process.stdout.fileno()
        while remaining > 0:
            wait_sec = deadline - time.monotonic()
            if wait_sec <= 0:
                return False, None
            if self.selector is None or not self.selector.select(wait_sec):
                return False, None
            chunk = os.read(fd, remaining)
            if not chunk:
                return False, None
            chunks.append(chunk)
            remaining -= len(chunk)
        frame = np.frombuffer(b"".join(chunks), dtype=np.uint8)
        frame = frame.reshape((self.frame_height, self.frame_width, 3))
        return True, frame.copy()

    def release(self) -> None:
        if self.selector is not None:
            try:
                self.selector.close()
            except Exception:
                pass
            self.selector = None
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None


def open_stream_capture(args: argparse.Namespace) -> Any:
    if args.capture_backend == "opencv":
        return OpenCvStreamCapture(
            args.rtmp_url,
            read_timeout_sec=args.stream_read_timeout_sec,
        )
    return FfmpegRawFrameCapture(
        rtmp_url=args.rtmp_url,
        ffmpeg_bin=args.ffmpeg_bin,
        sample_fps=args.sample_fps,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        read_timeout_sec=args.stream_read_timeout_sec,
        avfoundation_framerate=args.avfoundation_framerate,
        ffmpeg_realtime_input=args.ffmpeg_realtime_input,
    )
