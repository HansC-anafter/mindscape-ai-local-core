#!/bin/bash
# Setup script for Unsplash Dataset fingerprints
# This script can be run manually or integrated into installation process

set -e

# Get absolute paths to ensure script works from any directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${DATA_DIR:-$PROJECT_ROOT/data/unsplash-dataset}"

# Verify project structure
if [ ! -d "$PROJECT_ROOT/backend" ]; then
    echo "Error: Invalid project structure. Expected 'backend' directory at $PROJECT_ROOT/backend"
    echo "Please ensure you're running this script from the mindscape-ai-local-core project."
    exit 1
fi

echo "=== Unsplash Dataset Fingerprints Setup ==="
echo "Project root: $PROJECT_ROOT"
echo "Data directory: $DATA_DIR"
echo ""

# Check if Hugging Face CLI is installed
if ! command -v huggingface-cli &> /dev/null; then
    echo "Installing huggingface_hub..."
    pip install huggingface_hub
fi

# Check for Hugging Face token
if [ -z "$HF_TOKEN" ]; then
    echo "Warning: HF_TOKEN not set. You may need to login:"
    echo "  huggingface-cli login"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create data directory
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

echo "Downloading Unsplash Dataset from Hugging Face..."
echo "This may take several minutes depending on your connection..."
echo ""

# Download TSV files
huggingface-cli download image-search-2/unsplash_lite_image_dataset \
    colors.tsv keywords.tsv photos.tsv collections.tsv \
    --repo-type dataset \
    --local-dir "$DATA_DIR" \
    --local-dir-use-symlinks False

echo ""
echo "Download complete. Files saved to: $DATA_DIR"
echo ""

# Check if files exist
if [ ! -f "$DATA_DIR/colors.tsv" ] || [ ! -f "$DATA_DIR/keywords.tsv" ]; then
    echo "Error: Required TSV files not found. Download may have failed."
    exit 1
fi

echo "Building fingerprints database..."
cd "$PROJECT_ROOT"

# Run fingerprint builder (use absolute path to ensure it works from any directory)
PYTHON_SCRIPT="$PROJECT_ROOT/backend/scripts/build_unsplash_fingerprints.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Script not found at $PYTHON_SCRIPT"
    exit 1
fi

python "$PYTHON_SCRIPT" \
    --colors "$DATA_DIR/colors.tsv" \
    --keywords "$DATA_DIR/keywords.tsv" \
    --photos "$DATA_DIR/photos.tsv" \
    --collections "$DATA_DIR/collections.tsv" \
    --batch-size 1000

echo ""
echo "=== Setup Complete ==="
echo "Fingerprints database is ready for use."
echo ""
echo "To verify, run:"
echo "  docker exec -it mindscape-ai-local-core-postgres-1 psql -U mindscape -d mindscape_vectors -c 'SELECT COUNT(*) FROM unsplash_photo_fingerprints;'"

