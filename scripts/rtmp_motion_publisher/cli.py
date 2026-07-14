from __future__ import annotations

import argparse

from .settings import (
    DEFAULT_API_RETRY_BACKOFF_SEC,
    DEFAULT_API_RETRY_COUNT,
    DEFAULT_API_TIMEOUT_SEC,
    DEFAULT_CLOSEOUT_API_TIMEOUT_SEC,
    DEFAULT_ROLLUP_API_TIMEOUT_SEC,
    DEFAULT_APPEND_QUEUE_MAX_SIZE,
    DEFAULT_AVFOUNDATION_FRAMERATE,
    DEFAULT_CAPTURE_BACKEND,
    DEFAULT_FFMPEG_BIN,
    DEFAULT_FFMPEG_REALTIME_INPUT,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_MAX_SAMPLES,
    DEFAULT_MODEL_ASSET_PATH,
    DEFAULT_ROLLUP_EVERY_SEC,
    DEFAULT_SAMPLE_FPS,
    DEFAULT_STATUS_EVERY_SEC,
    DEFAULT_STREAM_GAP_HOLDOVER_CONFIDENCE_CAP,
    DEFAULT_STREAM_GAP_HOLDOVER_SEC,
    DEFAULT_STREAM_READ_FAILURE_THRESHOLD,
    DEFAULT_STREAM_READ_TIMEOUT_SEC,
    DEFAULT_STREAM_RECONNECT_BACKOFF_SEC,
    DEFAULT_WINDOW_SEC,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish compact MediaPipe pose windows from one live media input.",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-url")
    input_group.add_argument("--rtmp-url")
    parser.add_argument("--transport-kind", default="local_rtmp")
    parser.add_argument("--source-kind", default="external_stream")
    parser.add_argument("--api-base", default="http://localhost:8200")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--source-session-id", required=True)
    parser.add_argument("--live-session-id")
    parser.add_argument("--practice-session-id")
    parser.add_argument("--duration-sec", type=float, default=0.0)
    parser.add_argument("--sample-fps", type=float, default=DEFAULT_SAMPLE_FPS)
    parser.add_argument("--window-sec", type=float, default=DEFAULT_WINDOW_SEC)
    parser.add_argument("--max-samples", type=int, default=DEFAULT_MAX_SAMPLES)
    parser.add_argument("--status-every-sec", type=float, default=DEFAULT_STATUS_EVERY_SEC)
    parser.add_argument("--rollup-every-sec", type=float, default=DEFAULT_ROLLUP_EVERY_SEC)
    parser.add_argument("--expected-duration-ms", type=float, default=0.0)
    parser.add_argument(
        "--stream-cost-provider",
        default="local",
        help="Provider rate card to quote at stream start, for example local or gcp.",
    )
    parser.add_argument(
        "--stream-cost-region",
        default="",
        help="Provider region; GCP defaults to asia-east1 when omitted.",
    )
    parser.add_argument(
        "--stream-cost-direction",
        choices=["remote_pull", "input"],
        default="remote_pull",
    )
    parser.add_argument(
        "--stream-cost-transport",
        default="",
        help="Defaults to the source URI scheme.",
    )
    parser.add_argument("--stream-cost-codec", default="h264")
    parser.add_argument(
        "--stream-cost-billing-tier",
        choices=["sd", "hd", "uhd"],
        default=None,
        help="Provider billing tier when analysis frames are downscaled from the source.",
    )
    parser.add_argument("--stream-cost-source-width", type=int, default=0)
    parser.add_argument("--stream-cost-source-height", type=int, default=0)
    parser.add_argument("--stream-cost-source-fps", type=float, default=0.0)
    parser.add_argument("--stream-cost-source-bitrate-mbps", type=float, default=0.0)
    parser.add_argument("--disable-stream-cost", action="store_true")
    parser.add_argument("--max-window-refs", type=int, default=100)
    parser.add_argument("--model-asset-path", default=str(DEFAULT_MODEL_ASSET_PATH))
    parser.add_argument("--api-timeout-sec", type=float, default=DEFAULT_API_TIMEOUT_SEC)
    parser.add_argument(
        "--rollup-api-timeout-sec",
        type=float,
        default=DEFAULT_ROLLUP_API_TIMEOUT_SEC,
    )
    parser.add_argument(
        "--closeout-api-timeout-sec",
        type=float,
        default=DEFAULT_CLOSEOUT_API_TIMEOUT_SEC,
    )
    parser.add_argument("--api-retry-count", type=int, default=DEFAULT_API_RETRY_COUNT)
    parser.add_argument(
        "--api-retry-backoff-sec",
        type=float,
        default=DEFAULT_API_RETRY_BACKOFF_SEC,
    )
    parser.add_argument(
        "--append-queue-max-size",
        type=int,
        default=DEFAULT_APPEND_QUEUE_MAX_SIZE,
    )
    parser.add_argument(
        "--capture-backend",
        choices=["ffmpeg", "opencv"],
        default=DEFAULT_CAPTURE_BACKEND,
    )
    parser.add_argument("--ffmpeg-bin", default=DEFAULT_FFMPEG_BIN)
    parser.add_argument(
        "--ffmpeg-realtime-input",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_FFMPEG_REALTIME_INPUT,
        help="Pass -re before ffmpeg input so local files are consumed in wall-clock time.",
    )
    parser.add_argument("--frame-width", type=int, default=DEFAULT_FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=DEFAULT_FRAME_HEIGHT)
    parser.add_argument(
        "--avfoundation-framerate",
        type=float,
        default=DEFAULT_AVFOUNDATION_FRAMERATE,
    )
    parser.add_argument(
        "--stream-read-timeout-sec",
        type=float,
        default=DEFAULT_STREAM_READ_TIMEOUT_SEC,
    )
    parser.add_argument(
        "--stream-read-failure-threshold",
        type=int,
        default=DEFAULT_STREAM_READ_FAILURE_THRESHOLD,
    )
    parser.add_argument(
        "--stream-reconnect-backoff-sec",
        type=float,
        default=DEFAULT_STREAM_RECONNECT_BACKOFF_SEC,
    )
    parser.add_argument(
        "--stream-reconnect-max-attempts",
        type=int,
        default=0,
        help="0 means retry until the publisher is stopped.",
    )
    parser.add_argument(
        "--source-wait-timeout-sec",
        type=float,
        default=0.0,
        help="Maximum initial publisher wait; 0 is bounded only by explicit stop.",
    )
    parser.add_argument(
        "--stream-gap-holdover-sec",
        type=float,
        default=DEFAULT_STREAM_GAP_HOLDOVER_SEC,
    )
    parser.add_argument(
        "--stream-gap-holdover-confidence-cap",
        type=float,
        default=DEFAULT_STREAM_GAP_HOLDOVER_CONFIDENCE_CAP,
    )
    parser.add_argument("--disable-guidance-ws", action="store_true")
    parser.add_argument("--emit-yogacoach-summary", action="store_true")
    parser.add_argument("--yogacoach-reference-url", default="")
    parser.add_argument("--motion-reference-profile-path", default="")
    parser.add_argument("--motion-reference-profile-artifact-id", default="")
    parser.add_argument("--yogacoach-summary-output-dir", default="")
    parser.add_argument("--materialize-practice-diary", action="store_true")
    parser.add_argument("--practice-diary-reference-visual-evidence-path", default="")
    parser.add_argument("--user-id", default="default-user")
    parser.add_argument("--user-goal", default="")
    parser.add_argument("--event-log-path", default="")
    parser.add_argument("--append-owner-id", default="")
    parser.add_argument("--receiver-identity", default="")
    parser.add_argument("--media-session-id", default="")
    parser.add_argument("--receiver-state-path", default="")
    parser.add_argument("--disable-learner-visual-evidence", action="store_true")
    parser.add_argument("--learner-evidence-output-dir", default="")
    parser.add_argument("--learner-evidence-storage-dir", default="")
    parser.add_argument("--learner-evidence-max-windows", type=int, default=1200)
    parser.add_argument("--learner-evidence-jpeg-quality", type=int, default=78)
    args = parser.parse_args(argv)
    args.rtmp_url = str(args.input_url or args.rtmp_url)
    return args
