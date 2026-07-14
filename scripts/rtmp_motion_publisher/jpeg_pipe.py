from __future__ import annotations


JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"


class BoundedJpegFrameParser:
    """Recover complete JPEG frames without allowing an unbounded pipe buffer."""

    def __init__(self, *, max_frame_bytes: int) -> None:
        self.max_frame_bytes = max(1024, int(max_frame_bytes))
        self._buffer = bytearray()
        self.discarded_bytes = 0
        self.overflow_count = 0
        self.high_watermark_bytes = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, payload: bytes) -> None:
        if not payload:
            return
        self._buffer.extend(payload)
        self.high_watermark_bytes = max(
            self.high_watermark_bytes,
            len(self._buffer),
        )

    def pop_frame(self) -> bytes | None:
        frame_start = self._buffer.find(JPEG_START)
        if frame_start < 0:
            self._discard_without_losing_split_marker()
            return None
        if frame_start > 0:
            self._discard_prefix(frame_start)

        frame_end = self._buffer.find(JPEG_END, len(JPEG_START))
        if frame_end >= 0:
            payload_end = frame_end + len(JPEG_END)
            if payload_end > self.max_frame_bytes:
                self.overflow_count += 1
                latest_start = self._buffer.rfind(
                    JPEG_START,
                    len(JPEG_START),
                    payload_end,
                )
                if latest_start > 0:
                    self._discard_prefix(latest_start)
                else:
                    self._discard_without_losing_split_marker()
                return None
            payload = bytes(self._buffer[:payload_end])
            del self._buffer[:payload_end]
            return payload

        if len(self._buffer) > self.max_frame_bytes:
            self.overflow_count += 1
            latest_start = self._buffer.rfind(JPEG_START, len(JPEG_START))
            if latest_start > 0:
                self._discard_prefix(latest_start)
            if len(self._buffer) > self.max_frame_bytes:
                self._discard_without_losing_split_marker()
        return None

    def _discard_prefix(self, size: int) -> None:
        if size <= 0:
            return
        del self._buffer[:size]
        self.discarded_bytes += size

    def _discard_without_losing_split_marker(self) -> None:
        keep = 1 if self._buffer.endswith(JPEG_START[:1]) else 0
        discard = len(self._buffer) - keep
        self._discard_prefix(discard)


__all__ = ["BoundedJpegFrameParser"]
