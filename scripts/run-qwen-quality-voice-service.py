#!/usr/bin/env python3
"""Thin executable seam for the Qwen quality-voice host runtime."""

from backend.app.services.host_services.qwen_quality_voice_runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
