from __future__ import annotations

from scripts.rtmp_motion_publisher.jpeg_pipe import BoundedJpegFrameParser


def _jpeg(payload: bytes) -> bytes:
    return b"\xff\xd8" + payload + b"\xff\xd9"


def test_parser_recovers_frames_split_across_pipe_reads() -> None:
    parser = BoundedJpegFrameParser(max_frame_bytes=1024)
    frame = _jpeg(b"frame-one")

    parser.feed(frame[:1])
    assert parser.pop_frame() is None
    parser.feed(frame[1:7])
    assert parser.pop_frame() is None
    parser.feed(frame[7:])

    assert parser.pop_frame() == frame
    assert parser.buffered_bytes == 0
    assert parser.overflow_count == 0


def test_parser_preserves_multiple_frames_from_one_pipe_read() -> None:
    parser = BoundedJpegFrameParser(max_frame_bytes=1024)
    first = _jpeg(b"first")
    second = _jpeg(b"second")

    parser.feed(first + second)

    assert parser.pop_frame() == first
    assert parser.pop_frame() == second
    assert parser.pop_frame() is None


def test_parser_discards_noise_and_resynchronizes_at_jpeg_marker() -> None:
    parser = BoundedJpegFrameParser(max_frame_bytes=1024)
    frame = _jpeg(b"valid")

    parser.feed(b"transport-noise" + frame)

    assert parser.pop_frame() == frame
    assert parser.discarded_bytes == len(b"transport-noise")


def test_parser_bounds_malformed_frame_and_recovers_latest_marker() -> None:
    parser = BoundedJpegFrameParser(max_frame_bytes=1024)
    valid = _jpeg(b"valid")

    parser.feed(b"\xff\xd8" + b"x" * 1100 + valid)

    assert parser.pop_frame() is None
    assert parser.overflow_count == 1
    assert parser.buffered_bytes <= parser.max_frame_bytes
    assert parser.pop_frame() == valid
