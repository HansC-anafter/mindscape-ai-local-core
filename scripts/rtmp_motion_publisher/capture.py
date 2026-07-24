from __future__ import annotations

import argparse
import os
import queue
import selectors
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .events import emit
from .jpeg_pipe import BoundedJpegFrameParser


JPEG_PIPE_READ_SIZE = 64 * 1024
JPEG_PIPE_MAX_FRAME_BYTES = 2 * 1024 * 1024
DEFAULT_PROCESS_STOP_TIMEOUT_SEC = 2.0
RETAINED_VIDEO_FINALIZE_TIMEOUT_SEC = 30.0


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
        retained_video_path: str | Path | None = None,
    ) -> None:
        self.rtmp_url = rtmp_url
        self.ffmpeg_bin = ffmpeg_bin
        self.sample_fps = sample_fps
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.read_timeout_sec = read_timeout_sec
        self.avfoundation_framerate = avfoundation_framerate
        self.ffmpeg_realtime_input = ffmpeg_realtime_input
        self.retained_video_path = (
            Path(retained_video_path).expanduser()
            if retained_video_path
            else None
        )
        self.process: subprocess.Popen[bytes] | None = None
        self.selector: selectors.BaseSelector | None = None
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._jpeg_parser = BoundedJpegFrameParser(
            max_frame_bytes=JPEG_PIPE_MAX_FRAME_BYTES
        )
        self._stop_reader = threading.Event()
        self._reader_done = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._decoded_frames = 0
        self._overwritten_frames = 0
        self._decode_errors = 0
        self._pipe_bytes_read = 0
        self._pipe_idle_timeout_count = 0
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
        retained_output: list[str] = []
        if self.retained_video_path is not None:
            self.retained_video_path.parent.mkdir(parents=True, exist_ok=True)
            retained_output = [
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                "-y",
                str(self.retained_video_path),
            ]
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
            *retained_output,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={fps},scale={self.frame_width}:{self.frame_height}",
            "-c:v",
            "mjpeg",
            "-q:v",
            "4",
            "-f",
            "image2pipe",
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
        deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
        fd = self.process.stdout.fileno()
        while not self._stop_reader.is_set():
            encoded_frame = self._jpeg_parser.pop_frame()
            if encoded_frame is not None:
                return encoded_frame
            wait_sec = deadline - time.monotonic()
            if wait_sec <= 0:
                if self.process.poll() is not None:
                    self._reader_error = f"ffmpeg_exit_{self.process.returncode}"
                    return None
                self._pipe_idle_timeout_count += 1
                self._reader_error = "frame_pipe_idle"
                deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
                continue
            try:
                readable = self.selector is not None and self.selector.select(wait_sec)
            except (OSError, ValueError):
                self._reader_error = "frame_pipe_selector_failed"
                return None
            if not readable:
                if self.process.poll() is not None:
                    self._reader_error = f"ffmpeg_exit_{self.process.returncode}"
                    return None
                self._pipe_idle_timeout_count += 1
                self._reader_error = "frame_pipe_idle"
                deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
                continue
            try:
                chunk = os.read(fd, JPEG_PIPE_READ_SIZE)
            except OSError:
                self._reader_error = "frame_pipe_read_failed"
                return None
            if not chunk:
                return_code = self.process.poll()
                self._reader_error = (
                    f"ffmpeg_exit_{return_code}"
                    if return_code is not None
                    else "frame_pipe_eof"
                )
                return None
            self._reader_error = None
            self._pipe_bytes_read += len(chunk)
            self._jpeg_parser.feed(chunk)
            deadline = time.monotonic() + max(1.0, self.read_timeout_sec)
        return None

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
                frame = cv2.imdecode(
                    np.frombuffer(payload, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is None or frame.shape[:2] != (
                    self.frame_height,
                    self.frame_width,
                ):
                    self._decode_errors += 1
                    continue
                self._decoded_frames += 1
                self._replace_latest_frame(frame)
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
            "decode_errors": self._decode_errors,
            "pipe_bytes_read": self._pipe_bytes_read,
            "pipe_buffered_bytes": self._jpeg_parser.buffered_bytes,
            "pipe_high_watermark_bytes": self._jpeg_parser.high_watermark_bytes,
            "pipe_discarded_bytes": self._jpeg_parser.discarded_bytes,
            "pipe_overflow_count": self._jpeg_parser.overflow_count,
            "pipe_idle_timeout_count": self._pipe_idle_timeout_count,
            "reader_error": self._reader_error,
        }

    def release(self) -> None:
        if self.process is None:
            self._stop_reader.set()
            return
        if self.process.poll() is None:
            self.process.terminate()
            finalize_timeout_sec = (
                RETAINED_VIDEO_FINALIZE_TIMEOUT_SEC
                if self.retained_video_path is not None
                else DEFAULT_PROCESS_STOP_TIMEOUT_SEC
            )
            try:
                self.process.wait(timeout=finalize_timeout_sec)
            except subprocess.TimeoutExpired:
                self._stop_reader.set()
                self.process.kill()
                self.process.wait(timeout=DEFAULT_PROCESS_STOP_TIMEOUT_SEC)
        self._stop_reader.set()
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
    retained_video_path = None
    evidence_dir = str(
        getattr(args, "learner_evidence_output_dir", "") or ""
    ).strip()
    input_uri = str(getattr(args, "rtmp_url", "") or "").strip().lower()
    if (
        evidence_dir
        and not bool(getattr(args, "disable_learner_visual_evidence", False))
        and input_uri.startswith(
            ("rtmp://", "rtmps://", "rtsp://", "rtsps://", "avfoundation:")
        )
    ):
        part_index = int(getattr(args, "_learner_retained_video_part_index", 0))
        setattr(args, "_learner_retained_video_part_index", part_index + 1)
        retained_video_path = (
            Path(evidence_dir).expanduser()
            / f"learner-capture-part-{part_index:03d}.mp4"
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
        retained_video_path=retained_video_path,
    )
