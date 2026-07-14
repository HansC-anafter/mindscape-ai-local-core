from __future__ import annotations

import argparse
import os
import queue
import selectors
import subprocess
import threading
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
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._stop_reader = threading.Event()
        self._reader_done = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._decoded_frames = 0
        self._overwritten_frames = 0
        self._reader_error: str | None = None
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
            self._reader_thread = threading.Thread(
                target=self._drain_frames,
                name="motion-media-frame-drain",
                daemon=True,
            )
            self._reader_thread.start()

    def isOpened(self) -> bool:
        if self.process is None or self.process.stdout is None or self.selector is None:
            return False
        return not self._frames.empty() or (
            self.process.poll() is None and not self._reader_done.is_set()
        )

    def _read_frame_bytes(self) -> bytes | None:
        if self.process is None or self.process.stdout is None:
            return None
        chunks: list[bytes] = []
        remaining = self.frame_size
        deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
        fd = self.process.stdout.fileno()
        while remaining > 0 and not self._stop_reader.is_set():
            wait_sec = deadline - time.monotonic()
            if wait_sec <= 0:
                self._reader_error = "frame_read_timeout"
                return None
            try:
                readable = self.selector is not None and self.selector.select(wait_sec)
            except (OSError, ValueError):
                return None
            if not readable:
                self._reader_error = "frame_read_timeout"
                return None
            try:
                chunk = os.read(fd, remaining)
            except OSError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining > 0:
            return None
        return b"".join(chunks)

    def _replace_latest_frame(self, frame: np.ndarray) -> None:
        while not self._stop_reader.is_set():
            try:
                self._frames.put_nowait(frame)
                return
            except queue.Full:
                try:
                    self._frames.get_nowait()
                except queue.Empty:
                    continue
                self._overwritten_frames += 1

    def _drain_frames(self) -> None:
        try:
            while not self._stop_reader.is_set():
                payload = self._read_frame_bytes()
                if payload is None:
                    return
                frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                    (self.frame_height, self.frame_width, 3)
                )
                self._decoded_frames += 1
                self._replace_latest_frame(frame.copy())
        finally:
            self._reader_done.set()

    def read(self) -> tuple[bool, Any]:
        if self.process is None:
            return False, None
        deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
        while True:
            if self._reader_done.is_set() and self._frames.empty():
                return False, None
            wait_sec = deadline - time.monotonic()
            if wait_sec <= 0:
                return False, None
            try:
                return True, self._frames.get(timeout=min(0.1, wait_sec))
            except queue.Empty:
                continue

    def stats(self) -> dict[str, int | str | None]:
        return {
            "decoded_frames": self._decoded_frames,
            "overwritten_frames": self._overwritten_frames,
            "reader_error": self._reader_error,
        }

    def release(self) -> None:
        self._stop_reader.set()
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None
        if self.selector is not None:
            try:
                self.selector.close()
            except Exception:
                pass
            self.selector = None
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
