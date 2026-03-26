#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

from laf_host_runtime_common import fetch_remote_bytes, resolve_model_weight_artifact


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--mask-path", default="")
    parser.add_argument("--mask-url", default="")
    parser.add_argument("--bbox-json", default="")
    parser.add_argument("--bbox-source", default="")
    parser.add_argument("--context-mode", default="")
    return parser.parse_args()


def _load_image_rgb(*, image_path: str, image_url: str):
    import numpy as np
    from PIL import Image

    if image_path:
        image = Image.open(image_path).convert("RGB")
        return np.asarray(image)

    if not image_url:
        raise ValueError("image_path or image_url is required")

    payload = fetch_remote_bytes(image_url)
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    return np.asarray(image)


def _load_mask_gray(*, mask_path: str, mask_url: str):
    import numpy as np
    from PIL import Image

    if mask_path:
        mask = Image.open(mask_path).convert("L")
        return np.asarray(mask)

    if not mask_url:
        raise ValueError("mask_path or mask_url is required")

    payload = fetch_remote_bytes(mask_url)
    mask = Image.open(io.BytesIO(payload)).convert("L")
    return np.asarray(mask)


def _resolve_bbox(mask: "np.ndarray", bbox_json: str) -> dict[str, int]:
    import numpy as np

    if bbox_json:
        bbox = json.loads(bbox_json)
        return {
            "x": int(bbox["x"]),
            "y": int(bbox["y"]),
            "width": int(bbox["width"]),
            "height": int(bbox["height"]),
        }

    coords = np.argwhere(mask > 0)
    if coords.size == 0:
        raise ValueError("mask contains no selected pixels")
    top = int(coords[:, 0].min())
    bottom = int(coords[:, 0].max()) + 1
    left = int(coords[:, 1].min())
    right = int(coords[:, 1].max()) + 1
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def _normalize_bbox_source(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"impact_region_bbox", "coarse_mask_bbox"}:
        return normalized
    return "coarse_mask_bbox"


def _normalize_context_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"contact_zone", "local_scene", "object_only"}:
        return normalized
    return "object_only"


def _margin_ratio_for_context_mode(context_mode: str) -> float:
    normalized = _normalize_context_mode(context_mode)
    if normalized == "contact_zone":
        return 0.22
    if normalized == "local_scene":
        return 0.1
    return 0.15


def _expand_bbox(bbox: dict[str, int], width: int, height: int, margin_ratio: float = 0.15) -> dict[str, int]:
    margin_x = max(int(bbox["width"] * margin_ratio), 8)
    margin_y = max(int(bbox["height"] * margin_ratio), 8)
    left = max(bbox["x"] - margin_x, 0)
    top = max(bbox["y"] - margin_y, 0)
    right = min(bbox["x"] + bbox["width"] + margin_x, width)
    bottom = min(bbox["y"] + bbox["height"] + margin_y, height)
    return {
        "x": left,
        "y": top,
        "width": max(right - left, 1),
        "height": max(bottom - top, 1),
    }


def _crop_box_from_bbox(
    bbox: dict[str, int],
    *,
    width: int,
    height: int,
    context_mode: str,
) -> dict[str, int]:
    return _expand_bbox(
        bbox,
        width,
        height,
        margin_ratio=_margin_ratio_for_context_mode(context_mode),
    )


def _resolve_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_modnet(device: str):
    import torch
    from src.models.modnet import MODNet

    checkpoint = resolve_model_weight_artifact("modnet")
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if isinstance(state, dict) and isinstance(state.get("state_dict"), dict):
        state = state["state_dict"]
    if not isinstance(state, dict):
        raise ValueError("Unsupported MODNet checkpoint format")
    normalized_state = {
        str(key).replace("module.", "", 1): value for key, value in state.items()
    }

    model = MODNet(backbone_pretrained=False)
    model.load_state_dict(normalized_state)
    model = model.to(device)
    model.eval()
    return model, checkpoint


def _predict_matte(model, image_rgb, bbox: dict[str, int], device: str, *, context_mode: str):
    import cv2
    import numpy as np
    import torch
    import torch.nn.functional as F
    import torchvision.transforms as transforms
    from PIL import Image

    height, width = image_rgb.shape[:2]
    expanded = _crop_box_from_bbox(
        bbox,
        width=width,
        height=height,
        context_mode=context_mode,
    )
    x, y, w, h = expanded["x"], expanded["y"], expanded["width"], expanded["height"]
    crop = image_rgb[y : y + h, x : x + w, :]

    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
        ]
    )
    tensor = transform(Image.fromarray(crop))[None, :, :, :]
    _, _, im_h, im_w = tensor.shape
    ref_size = 512
    if max(im_h, im_w) < ref_size or min(im_h, im_w) > ref_size:
        if im_w >= im_h:
            im_rh = ref_size
            im_rw = int(im_w / im_h * ref_size)
        else:
            im_rw = ref_size
            im_rh = int(im_h / im_w * ref_size)
    else:
        im_rh = im_h
        im_rw = im_w
    im_rw = max(im_rw - im_rw % 32, 32)
    im_rh = max(im_rh - im_rh % 32, 32)
    tensor = F.interpolate(tensor, size=(im_rh, im_rw), mode="area")

    with torch.no_grad():
        _, _, matte = model(tensor.to(device), True)

    matte = F.interpolate(matte, size=(im_h, im_w), mode="area")
    matte = matte[0][0].detach().cpu().numpy()
    matte = np.clip(matte, 0.0, 1.0)
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y : y + h, x : x + w] = np.clip(matte * 255.0, 0, 255).astype("uint8")
    return full_mask, expanded


def _blend_with_coarse_mask(refined_mask, coarse_mask):
    import cv2
    import numpy as np

    coarse_binary = (coarse_mask > 0).astype("uint8") * 255
    kernel = np.ones((7, 7), dtype=np.uint8)
    dilated = cv2.dilate(coarse_binary, kernel, iterations=2)
    refined = cv2.bitwise_and(refined_mask, dilated)
    merged = np.maximum(refined, (coarse_binary * 0.25).astype("uint8"))
    return np.clip(merged, 0, 255).astype("uint8")


def _bbox_from_mask(mask_binary) -> dict[str, int] | None:
    import numpy as np

    coords = np.argwhere(mask_binary > 0)
    if coords.size == 0:
        return None
    top = int(coords[:, 0].min())
    bottom = int(coords[:, 0].max()) + 1
    left = int(coords[:, 1].min())
    right = int(coords[:, 1].max()) + 1
    return {
        "x": left,
        "y": top,
        "width": max(right - left, 1),
        "height": max(bottom - top, 1),
    }


def main() -> int:
    try:
        args = _parse_args()
        image_rgb = _load_image_rgb(
            image_path=str(args.image_path or "").strip(),
            image_url=str(args.image_url or "").strip(),
        )
        coarse_mask = _load_mask_gray(
            mask_path=str(args.mask_path or "").strip(),
            mask_url=str(args.mask_url or "").strip(),
        )
        if coarse_mask.ndim != 2:
            raise ValueError("mask must be grayscale")

        bbox = _resolve_bbox(coarse_mask, str(args.bbox_json or "").strip())
        bbox_source = _normalize_bbox_source(str(args.bbox_source or "").strip())
        context_mode = _normalize_context_mode(str(args.context_mode or "").strip())
        requested_device = _resolve_device()
        device = requested_device
        model, checkpoint = _load_modnet(device)
        try:
            refined_mask, crop_box = _predict_matte(
                model,
                image_rgb,
                bbox,
                device,
                context_mode=context_mode,
            )
        except Exception as exc:
            if device == "mps" and "Adaptive pool MPS" in str(exc):
                device = "cpu"
                model, checkpoint = _load_modnet(device)
                refined_mask, crop_box = _predict_matte(
                    model,
                    image_rgb,
                    bbox,
                    device,
                    context_mode=context_mode,
                )
            else:
                raise
        merged_mask = _blend_with_coarse_mask(refined_mask, coarse_mask)
        inferred_bbox = _bbox_from_mask(merged_mask)
        if inferred_bbox is None:
            raise RuntimeError("MODNet produced an empty matte")

        from PIL import Image

        output = io.BytesIO()
        Image.fromarray(merged_mask, mode="L").save(output, format="PNG")
        confidence = float(merged_mask.max()) / 255.0
        print(
            json.dumps(
                {
                    "status": "ok",
                    "proposal_method": "modnet_portrait_refine",
                    "bbox": inferred_bbox,
                    "confidence": round(max(0.0, min(1.0, confidence)), 4),
                    "mask_png_base64": base64.b64encode(output.getvalue()).decode("ascii"),
                    "input_bbox": bbox,
                    "bbox_source": bbox_source,
                    "context_mode": context_mode,
                    "crop_box": crop_box,
                    "device": device,
                    "requested_device": requested_device,
                    "checkpoint_path": str(checkpoint),
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
