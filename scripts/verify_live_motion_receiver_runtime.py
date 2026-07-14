#!/usr/bin/env python3
from __future__ import annotations

import json

import cv2
import mediapipe  # noqa: F401
import numpy  # noqa: F401
import requests  # noqa: F401
import websocket  # noqa: F401
from mediapipe.tasks import python as mediapipe_python
from mediapipe.tasks.python import vision

from rtmp_motion_publisher.settings import DEFAULT_MODEL_ASSET_PATH


def main() -> int:
    build = cv2.getBuildInformation()
    if "FFMPEG:                      YES" not in build:
        raise RuntimeError("opencv_ffmpeg_backend_unavailable")
    if not hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        raise RuntimeError("opencv_open_timeout_unavailable")
    if not hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        raise RuntimeError("opencv_read_timeout_unavailable")
    if not DEFAULT_MODEL_ASSET_PATH.is_file() or DEFAULT_MODEL_ASSET_PATH.stat().st_size <= 0:
        raise RuntimeError("pose_model_asset_unavailable")
    if not hasattr(mediapipe_python, "BaseOptions") or not hasattr(
        vision,
        "PoseLandmarker",
    ):
        raise RuntimeError("mediapipe_pose_runtime_unavailable")
    print(
        json.dumps(
            {
                "status": "ready",
                "cv2_version": cv2.__version__,
                "model_bytes": DEFAULT_MODEL_ASSET_PATH.stat().st_size,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
