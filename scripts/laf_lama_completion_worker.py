#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import os

os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

from laf_host_runtime_common import fetch_remote_bytes, resolve_model_weight_artifact


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--mask-path", default="")
    parser.add_argument("--mask-url", default="")
    parser.add_argument("--strategy", default="conservative")
    return parser.parse_args()


def _load_image_rgb(*, image_path: str, image_url: str):
    import numpy as np
    from PIL import Image

    if image_path:
        return np.asarray(Image.open(image_path).convert("RGB"))
    if not image_url:
        raise ValueError("image_path or image_url is required")
    payload = fetch_remote_bytes(image_url)
    return np.asarray(Image.open(io.BytesIO(payload)).convert("RGB"))


def _load_mask_gray(*, mask_path: str, mask_url: str):
    import numpy as np
    from PIL import Image

    if mask_path:
        return np.asarray(Image.open(mask_path).convert("L"))
    if not mask_url:
        raise ValueError("mask_path or mask_url is required")
    payload = fetch_remote_bytes(mask_url)
    return np.asarray(Image.open(io.BytesIO(payload)).convert("L"))


def _resolve_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _completion_confidence(mask_gray, strategy: str) -> float:
    import numpy as np

    mask_ratio = float((mask_gray > 0).sum()) / float(mask_gray.size or 1)
    base = 0.86 if strategy == "conservative" else 0.78
    penalty = min(mask_ratio * 0.5, 0.25)
    return round(max(0.55, min(0.95, base - penalty)), 4)


def main() -> int:
    try:
        args = _parse_args()
        image_rgb = _load_image_rgb(
            image_path=str(args.image_path or "").strip(),
            image_url=str(args.image_url or "").strip(),
        )
        mask_gray = _load_mask_gray(
            mask_path=str(args.mask_path or "").strip(),
            mask_url=str(args.mask_url or "").strip(),
        )
        strategy = str(args.strategy or "conservative").strip().lower()
        if strategy not in {"conservative", "aggressive"}:
            strategy = "conservative"

        import numpy as np
        import cv2
        import lama_cleaner.model.lama as lama_mod
        from lama_cleaner.model.lama import LaMa
        from lama_cleaner.schema import Config, HDStrategy, LDMSampler

        weight_path = resolve_model_weight_artifact("lama")
        lama_mod.LAMA_MODEL_URL = str(weight_path)
        requested_device = _resolve_device()
        model = LaMa(requested_device)
        device = str(getattr(model, "device", requested_device))
        config = Config(
            ldm_steps=1,
            ldm_sampler=LDMSampler.plms,
            hd_strategy=HDStrategy.ORIGINAL,
            hd_strategy_crop_margin=64 if strategy == "aggressive" else 32,
            hd_strategy_crop_trigger_size=1024 if strategy == "aggressive" else 768,
            hd_strategy_resize_limit=1024 if strategy == "aggressive" else 768,
        )
        result_bgr = model(image_rgb, mask_gray, config)
        result_rgb = cv2.cvtColor(np.clip(result_bgr, 0, 255).astype("uint8"), cv2.COLOR_BGR2RGB)

        from PIL import Image

        output = io.BytesIO()
        Image.fromarray(result_rgb, mode="RGB").save(output, format="PNG")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "completion_method": "lama_background_completion",
                    "completion_png_base64": base64.b64encode(output.getvalue()).decode("ascii"),
                    "confidence": _completion_confidence(mask_gray, strategy),
                    "device": device,
                    "requested_device": requested_device,
                    "checkpoint_path": str(weight_path),
                    "strategy": strategy,
                }
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
