#!/usr/bin/env bash

set -euo pipefail

MODE="${1:-all}"
BASE_DIR="${COMFYUI_BASE_DIR:-/Volumes/OWC Ultra 4T/comfyui}"
LISTEN="${COMFYUI_LISTEN:-0.0.0.0}"
HEALTH_HOST="${COMFYUI_HEALTH_HOST:-127.0.0.1}"
PORT="${COMFYUI_PORT:-8188}"
PYTHON_BIN="${COMFYUI_PYTHON_BIN:-$BASE_DIR/.venv/bin/python}"
MAIN_PY="${COMFYUI_MAIN_PY:-/Applications/ComfyUI.app/Contents/Resources/ComfyUI/main.py}"
LOG_FILE="${COMFYUI_LOG_FILE:-$BASE_DIR/comfyui_server.log}"
HEALTH_URL="http://${HEALTH_HOST}:${PORT}/system_stats"

CONTROLNET_AUX_REPO="https://github.com/Fannovel16/comfyui_controlnet_aux"

declare -A MODEL_URLS=(
  ["$BASE_DIR/models/checkpoints/sdxl_lightning_4step_unet.safetensors"]="https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_4step_unet.safetensors"
  ["$BASE_DIR/models/checkpoints/v1-5-pruned-emaonly.ckpt"]="https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.ckpt"
  ["$BASE_DIR/models/clip/clip_l.safetensors"]="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/text_encoder/model.fp16.safetensors"
  ["$BASE_DIR/models/clip/clip_g.safetensors"]="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/text_encoder_2/model.fp16.safetensors"
  ["$BASE_DIR/models/controlnet/control_v11p_sd15_openpose.safetensors"]="https://huggingface.co/lllyasviel/control_v11p_sd15_openpose/resolve/main/diffusion_pytorch_model.safetensors"
  ["$BASE_DIR/models/vae/sdxl_vae.safetensors"]="https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
)

download_if_missing() {
  local dest="$1"
  local url="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" ]]; then
    echo "exists: $dest"
    return 0
  fi
  echo "download: $url -> $dest"
  curl -L --fail --retry 5 --retry-delay 2 --retry-all-errors --continue-at - -o "$dest" "$url"
}

install_assets() {
  mkdir -p "$BASE_DIR/custom_nodes"

  if [[ -f "$BASE_DIR/models/controlnet/controlnet-openpose-sdxl-1.0.safetensors" && ! -f "$BASE_DIR/models/controlnet/control_v11p_sd15_openpose.safetensors" ]]; then
    echo "migrate: reuse existing SD1.5 controlnet under honest filename"
    cp "$BASE_DIR/models/controlnet/controlnet-openpose-sdxl-1.0.safetensors" "$BASE_DIR/models/controlnet/control_v11p_sd15_openpose.safetensors"
  fi

  if [[ -d "$BASE_DIR/custom_nodes/comfyui_controlnet_aux/.git" ]]; then
    echo "update: comfyui_controlnet_aux"
    git -C "$BASE_DIR/custom_nodes/comfyui_controlnet_aux" pull --ff-only
  elif [[ -d "$BASE_DIR/custom_nodes/comfyui_controlnet_aux" ]]; then
    echo "skip: custom node dir exists without git metadata: $BASE_DIR/custom_nodes/comfyui_controlnet_aux"
  else
    echo "clone: comfyui_controlnet_aux"
    git clone "$CONTROLNET_AUX_REPO" "$BASE_DIR/custom_nodes/comfyui_controlnet_aux"
  fi

  if [[ -f "$BASE_DIR/custom_nodes/comfyui_controlnet_aux/requirements.txt" ]]; then
    echo "install: comfyui_controlnet_aux requirements"
    "$PYTHON_BIN" -m pip install -r "$BASE_DIR/custom_nodes/comfyui_controlnet_aux/requirements.txt"
  fi

  for dest in "${!MODEL_URLS[@]}"; do
    download_if_missing "$dest" "${MODEL_URLS[$dest]}"
  done
}

restart_comfyui() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "python not found: $PYTHON_BIN" >&2
    return 1
  fi
  if [[ ! -f "$MAIN_PY" ]]; then
    echo "main.py not found: $MAIN_PY" >&2
    return 1
  fi

  pkill -f "main.py --listen $LISTEN --port $PORT .*--base-directory $BASE_DIR" || true
  sleep 2

  (
    cd "$(dirname "$MAIN_PY")"
    if command -v setsid >/dev/null 2>&1; then
      setsid "$PYTHON_BIN" "$(basename "$MAIN_PY")" \
        --listen "$LISTEN" \
        --port "$PORT" \
        --base-directory "$BASE_DIR" \
        --user-directory "$BASE_DIR/user" \
        --output-directory "$BASE_DIR/output" \
        --input-directory "$BASE_DIR/input" \
        --temp-directory "$BASE_DIR/temp" \
        --database-url "sqlite:////$BASE_DIR/user/comfyui.db" \
        --disable-auto-launch \
        >> "$LOG_FILE" 2>&1 </dev/null &
    else
      nohup "$PYTHON_BIN" "$(basename "$MAIN_PY")" \
        --listen "$LISTEN" \
        --port "$PORT" \
        --base-directory "$BASE_DIR" \
        --user-directory "$BASE_DIR/user" \
        --output-directory "$BASE_DIR/output" \
        --input-directory "$BASE_DIR/input" \
        --temp-directory "$BASE_DIR/temp" \
        --database-url "sqlite:////$BASE_DIR/user/comfyui.db" \
        --disable-auto-launch \
        >> "$LOG_FILE" 2>&1 </dev/null &
    fi
  )

  for _ in {1..20}; do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      echo "healthy: $HEALTH_URL"
      return 0
    fi
    sleep 2
  done

  echo "ComfyUI did not become healthy at $HEALTH_URL" >&2
  return 1
}

run_comfyui_foreground() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "python not found: $PYTHON_BIN" >&2
    return 1
  fi
  if [[ ! -f "$MAIN_PY" ]]; then
    echo "main.py not found: $MAIN_PY" >&2
    return 1
  fi

  pkill -f "main.py --listen $LISTEN --port $PORT .*--base-directory $BASE_DIR" || true
  sleep 2

  cd "$(dirname "$MAIN_PY")"
  exec "$PYTHON_BIN" "$(basename "$MAIN_PY")" \
    --listen "$LISTEN" \
    --port "$PORT" \
    --base-directory "$BASE_DIR" \
    --user-directory "$BASE_DIR/user" \
    --output-directory "$BASE_DIR/output" \
    --input-directory "$BASE_DIR/input" \
    --temp-directory "$BASE_DIR/temp" \
    --database-url "sqlite:////$BASE_DIR/user/comfyui.db" \
    --disable-auto-launch
}

case "$MODE" in
  install-assets)
    install_assets
    ;;
  restart)
    restart_comfyui
    ;;
  foreground)
    install_assets
    run_comfyui_foreground
    ;;
  all)
    install_assets
    restart_comfyui
    ;;
  *)
    echo "usage: $0 [install-assets|restart|foreground|all]" >&2
    exit 1
    ;;
esac
