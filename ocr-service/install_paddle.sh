#!/bin/bash
# Auto-install PaddlePaddle (GPU or CPU) based on availability

set -e

echo "Detecting system configuration..."

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)

echo "Platform: $OS $ARCH"

# Mac (Intel or Apple Silicon) - PaddlePaddle only supports CPU
if [ "$OS" = "Darwin" ]; then
    echo "macOS detected: PaddlePaddle only supports CPU on macOS (no Metal/GPU support)"
    echo "Installing paddlepaddle (CPU)..."
    pip install paddlepaddle
# Linux with NVIDIA GPU
elif command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected, attempting paddlepaddle-gpu..."
    pip install paddlepaddle-gpu || {
        echo "GPU version failed, falling back to CPU..."
        pip install paddlepaddle
    }
# Linux without GPU or other platforms
else
    echo "No GPU detected or unsupported platform, installing paddlepaddle (CPU)..."
    pip install paddlepaddle
fi

echo "PaddlePaddle installation completed"



