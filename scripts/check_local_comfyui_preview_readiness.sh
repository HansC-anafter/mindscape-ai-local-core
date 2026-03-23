#!/usr/bin/env bash

set -euo pipefail

COMFY_URL="${COMFY_URL:-http://127.0.0.1:8188}"
COMFY_BASE="${COMFY_BASE:-/Volumes/OWC Ultra 4T/comfyui}"

python3 - "$COMFY_URL" "$COMFY_BASE" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

comfy_url = sys.argv[1].rstrip("/")
comfy_base = Path(sys.argv[2])

required_nodes = {
    "text_preview": [
        "CheckpointLoaderSimple",
        "DualCLIPLoader",
        "CLIPTextEncode",
        "VAELoader",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
    "pose_preview": [
        "CheckpointLoaderSimple",
        "ControlNetLoader",
        "LoadImage",
        "CLIPTextEncode",
        "OpenposePreprocessor",
        "ControlNetApplyAdvanced",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
}

required_files = {
    "text_checkpoint": comfy_base / "models" / "checkpoints" / "sdxl_lightning_4step_unet.safetensors",
    "clip_l": comfy_base / "models" / "clip" / "clip_l.safetensors",
    "clip_g": comfy_base / "models" / "clip" / "clip_g.safetensors",
    "pose_checkpoint": comfy_base / "models" / "checkpoints" / "v1-5-pruned-emaonly.ckpt",
    "controlnet_openpose": comfy_base / "models" / "controlnet" / "control_v11p_sd15_openpose.safetensors",
    "vae": comfy_base / "models" / "vae" / "sdxl_vae.safetensors",
}

custom_nodes = {
    "controlnet_aux_dir": comfy_base / "custom_nodes" / "comfyui_controlnet_aux",
}

def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)

try:
    stats = fetch_json(f"{comfy_url}/system_stats")
    object_info = fetch_json(f"{comfy_url}/object_info")
    reachable = True
except Exception as exc:
    print(f"ComfyUI reachable: no ({exc})")
    sys.exit(1)

print("ComfyUI reachable: yes")
system = stats.get("system", {})
devices = stats.get("devices", [])
argv = system.get("argv", [])
device_summary = ", ".join(
    f"{device.get('name')}:{device.get('type')}" for device in devices
) or "none"
print(f"Device(s): {device_summary}")
print(f"Python: {system.get('python_version', 'unknown')}")
print(f"ComfyUI version: {system.get('comfyui_version', 'unknown')}")
print(f"Custom nodes disabled at launch: {'yes' if '--disable-all-custom-nodes' in argv else 'no'}")

print("\nRequired nodes")
for lane, nodes in required_nodes.items():
    missing = [node for node in nodes if node not in object_info]
    if missing:
        print(f"- {lane}: missing -> {', '.join(missing)}")
    else:
        print(f"- {lane}: ok")

print("\nRequired model files")
for label, path in required_files.items():
    print(f"- {label}: {'ok' if path.exists() else 'missing'} ({path})")

print("\nCustom node directories")
for label, path in custom_nodes.items():
    print(f"- {label}: {'ok' if path.exists() else 'missing'} ({path})")
PY
