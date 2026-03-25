#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

from laf_host_runtime_common import fetch_remote_bytes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-path", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--bbox-json", required=True)
    return parser.parse_args()


def _load_image_bgr(*, image_path: str, image_url: str):
    import cv2
    import numpy as np

    if image_path:
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Unable to read image_path: {image_path}")
        return image

    if not image_url:
        raise ValueError("image_path or image_url is required")

    payload = fetch_remote_bytes(image_url)
    buffer = np.frombuffer(payload, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to decode image from URL: {image_url}")
    return image


def _resolve_sam2_checkpoint_root() -> Path:
    home = Path.home() / ".mindscape" / "models"
    candidates = [
        home / "layer_asset_forge" / "sam2_hiera_large",
        home / "segmentation" / "by_pack" / "layer_asset_forge" / "sam2_hiera_large",
        home / "sam2_hiera_large",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                checkpoint = _resolve_checkpoint_file(candidate)
                if checkpoint.stat().st_size <= 64 and checkpoint.read_bytes().startswith(b"MOCK_DATA"):
                    continue
            except Exception:
                continue
            return candidate
    raise FileNotFoundError("SAM2 checkpoint root not found under ~/.mindscape/models")


def _resolve_checkpoint_file(checkpoint_root: Path) -> Path:
    for file in checkpoint_root.iterdir():
        if file.suffix in {".pt", ".pth", ".ckpt"}:
            return file
    raise FileNotFoundError(f"No SAM2 checkpoint file found in {checkpoint_root}")


def _resolve_config_name(checkpoint_name: str) -> str:
    lowered = checkpoint_name.lower()
    if "tiny" in lowered or "_t" in lowered:
        return "sam2_hiera_t.yaml"
    if "small" in lowered or "_s" in lowered:
        return "sam2_hiera_s.yaml"
    if "base_plus" in lowered or "b+" in lowered:
        return "sam2_hiera_b+.yaml"
    return "sam2_hiera_l.yaml"


def _resolve_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _bbox_from_mask(mask_binary) -> dict[str, int] | None:
    import numpy as np

    coords = np.argwhere(mask_binary > 0)
    if coords.size == 0:
        return None
    top = int(coords[:, 0].min())
    bottom = int(coords[:, 0].max()) + 1
    left = int(coords[:, 1].min())
    right = int(coords[:, 1].max()) + 1
    if right <= left or bottom <= top:
        return None
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def main() -> int:
    try:
        args = _parse_args()
        bbox = json.loads(args.bbox_json)
        image_bgr = _load_image_bgr(
            image_path=str(args.image_path or "").strip(),
            image_url=str(args.image_url or "").strip(),
        )

        import cv2
        import numpy as np
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        checkpoint_root = _resolve_sam2_checkpoint_root()
        checkpoint_file = _resolve_checkpoint_file(checkpoint_root)
        config_name = _resolve_config_name(checkpoint_file.name)
        device = _resolve_device()
        original_torch_load = torch.load
        try:
            def _compat_torch_load(*load_args, **load_kwargs):
                load_kwargs.setdefault("weights_only", False)
                return original_torch_load(*load_args, **load_kwargs)

            torch.load = _compat_torch_load
            predictor = SAM2ImagePredictor(
                build_sam2(
                    config_file=config_name,
                    ckpt_path=str(checkpoint_file),
                    device=device,
                    mode="eval",
                )
            )
        finally:
            torch.load = original_torch_load
        predictor.set_image(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        box = np.asarray(
            [
                float(bbox["x"]),
                float(bbox["y"]),
                float(bbox["x"] + bbox["width"]),
                float(bbox["y"] + bbox["height"]),
            ],
            dtype=np.float32,
        )
        masks, scores, _ = predictor.predict(box=box, multimask_output=True)
        if masks is None or len(masks) == 0:
            raise RuntimeError("SAM2 returned no masks")

        best_index = 0
        if scores is not None and len(scores):
            best_index = int(np.asarray(scores).argmax())
        mask_binary = ((np.asarray(masks[best_index]) > 0).astype("uint8")) * 255
        inferred_bbox = _bbox_from_mask(mask_binary)
        if inferred_bbox is None:
            raise RuntimeError("SAM2 produced an empty mask")
        ok, encoded = cv2.imencode(".png", mask_binary)
        if not ok:
            raise RuntimeError("Failed to encode mask PNG")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "proposal_method": "sam2_bbox_guided",
                    "bbox": inferred_bbox,
                    "confidence": float(np.asarray(scores)[best_index]) if scores is not None and len(scores) else 0.9,
                    "mask_png_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                    "device": device,
                    "checkpoint_path": str(checkpoint_file),
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
