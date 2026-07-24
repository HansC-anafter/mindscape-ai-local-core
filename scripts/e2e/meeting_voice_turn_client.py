#!/usr/bin/env python3
"""Submit one bounded WAV voice turn to an active Meeting Engine session."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--client-turn-id")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def build_url(api_base: str, workspace_id: str, meeting_id: str) -> str:
    return (
        f"{api_base.rstrip('/')}/api/v1/workspaces/"
        f"{quote(workspace_id, safe='')}/meetings/"
        f"{quote(meeting_id, safe='')}/voice-turns"
    )


def load_wav(path: Path) -> bytes:
    payload = path.expanduser().resolve().read_bytes()
    if not payload.startswith(b"RIFF") or payload[8:12] != b"WAVE":
        raise ValueError(f"not_a_wav_file:{path}")
    return payload


def submit_voice_turn(args: argparse.Namespace) -> dict[str, Any]:
    wav_bytes = load_wav(args.wav)
    client_turn_id = args.client_turn_id or f"e2e_voice_{uuid.uuid4().hex}"
    response = requests.post(
        build_url(args.api_base, args.workspace_id, args.meeting_id),
        json={
            "client_turn_id": client_turn_id,
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "mime_type": "audio/wav",
            "language": args.language,
            "origin_surface": "meeting_voice",
            "context_objects": [],
            "metadata": {
                "e2e": True,
                "source": "scripts/e2e/meeting_voice_turn_client.py",
            },
        },
        timeout=args.timeout_seconds,
    )
    try:
        payload: Any = response.json()
    except ValueError:
        payload = {"raw_response": response.text[:2000]}
    if not response.ok:
        raise RuntimeError(
            f"voice_turn_http_{response.status_code}:"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
    if not isinstance(payload, dict):
        raise RuntimeError("voice_turn_response_not_object")
    return payload


def write_output(payload: dict[str, Any], output_path: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output_path is not None:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def main() -> int:
    args = parse_args()
    try:
        payload = submit_voice_turn(args)
        write_output(payload, args.output)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
