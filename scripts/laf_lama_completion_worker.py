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
    parser.add_argument("--impact-region-bbox-json", default="")
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


def _mask_bbox(mask_gray):
    import numpy as np

    coords = np.argwhere(mask_gray > 0)
    if coords.size == 0:
        raise ValueError("mask contains no selected pixels")
    top = int(coords[:, 0].min())
    bottom = int(coords[:, 0].max()) + 1
    left = int(coords[:, 1].min())
    right = int(coords[:, 1].max()) + 1
    return left, top, right, bottom


def _expand_bbox(left: int, top: int, right: int, bottom: int, width: int, height: int, *, strategy: str):
    box_width = max(right - left, 1)
    box_height = max(bottom - top, 1)
    margin_ratio = 0.2 if strategy == "aggressive" else 0.12
    min_margin = 64 if strategy == "aggressive" else 32
    margin_x = max(int(box_width * margin_ratio), min_margin)
    margin_y = max(int(box_height * margin_ratio), min_margin)
    return (
        max(left - margin_x, 0),
        max(top - margin_y, 0),
        min(right + margin_x, width),
        min(bottom + margin_y, height),
    )


def _normalize_explicit_bbox(bbox_json: str, *, width: int, height: int):
    if not bbox_json:
        return None
    try:
        payload = json.loads(bbox_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        x = max(int(payload.get("x", 0)), 0)
        y = max(int(payload.get("y", 0)), 0)
        bbox_width = int(payload.get("width", 0))
        bbox_height = int(payload.get("height", 0))
    except (TypeError, ValueError):
        return None
    if bbox_width <= 0 or bbox_height <= 0:
        return None
    right = min(x + bbox_width, width)
    bottom = min(y + bbox_height, height)
    if right <= x or bottom <= y:
        return None
    return {
        "x": x,
        "y": y,
        "width": right - x,
        "height": bottom - y,
    }


def _crop_completion_inputs(image_rgb, mask_gray, *, strategy: str, impact_region_bbox_json: str = ""):
    height, width = image_rgb.shape[:2]
    explicit_bbox = _normalize_explicit_bbox(
        impact_region_bbox_json,
        width=width,
        height=height,
    )
    if explicit_bbox:
        x = explicit_bbox["x"]
        y = explicit_bbox["y"]
        crop_width = explicit_bbox["width"]
        crop_height = explicit_bbox["height"]
        return {
            "crop_box": explicit_bbox,
            "image_crop": image_rgb[y : y + crop_height, x : x + crop_width, :],
            "mask_crop": mask_gray[y : y + crop_height, x : x + crop_width],
            "crop_source": "impact_region_bbox",
        }

    left, top, right, bottom = _mask_bbox(mask_gray)
    crop_left, crop_top, crop_right, crop_bottom = _expand_bbox(
        left,
        top,
        right,
        bottom,
        width,
        height,
        strategy=strategy,
    )
    return {
        "crop_box": {
            "x": crop_left,
            "y": crop_top,
            "width": max(crop_right - crop_left, 1),
            "height": max(crop_bottom - crop_top, 1),
        },
        "image_crop": image_rgb[crop_top:crop_bottom, crop_left:crop_right, :],
        "mask_crop": mask_gray[crop_top:crop_bottom, crop_left:crop_right],
        "crop_source": "mask_bbox",
    }


def _merge_completion_crop(image_rgb, completion_rgb, crop_box):
    merged = image_rgb.copy()
    x = int(crop_box["x"])
    y = int(crop_box["y"])
    width = int(crop_box["width"])
    height = int(crop_box["height"])
    merged[y : y + height, x : x + width, :] = completion_rgb[:height, :width, :]
    return merged


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
        cropped_inputs = _crop_completion_inputs(
            image_rgb,
            mask_gray,
            strategy=strategy,
            impact_region_bbox_json=str(args.impact_region_bbox_json or "").strip(),
        )
        image_crop = cropped_inputs["image_crop"]
        mask_crop = cropped_inputs["mask_crop"]
        crop_box = cropped_inputs["crop_box"]
        crop_source = cropped_inputs["crop_source"]

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
        result_bgr = model(image_crop, mask_crop, config)
        result_rgb_crop = cv2.cvtColor(
            np.clip(result_bgr, 0, 255).astype("uint8"),
            cv2.COLOR_BGR2RGB,
        )
        result_rgb = _merge_completion_crop(image_rgb, result_rgb_crop, crop_box)

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
                    "crop_box": crop_box,
                    "crop_source": crop_source,
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
