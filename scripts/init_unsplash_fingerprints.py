"""
Optional initialization script for Unsplash Dataset fingerprints.

This script can be called during installation or setup to optionally
download and build the fingerprint database.

Usage:
    # As a module (from installation script)
    from scripts.init_unsplash_fingerprints import setup_fingerprints_if_enabled

    # Or directly
    python scripts/init_unsplash_fingerprints.py --auto-download
"""
import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_huggingface_cli() -> bool:
    """Check if huggingface-cli is available."""
    try:
        result = subprocess.run(
            ["huggingface-cli", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    try:
        result = subprocess.run(
            [sys.executable, "-m", "huggingface_hub.commands.huggingface_cli", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_huggingface_cli() -> bool:
    """Install huggingface_hub package."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "huggingface_hub"],
            check=True,
            capture_output=True
        )
        logger.info("Installed huggingface_hub")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install huggingface_hub: {e}")
        return False


def download_dataset(data_dir: Path, hf_token: Optional[str] = None) -> bool:
    """
    Download Unsplash Dataset from Hugging Face.

    Args:
        data_dir: Directory to save TSV files
        hf_token: Optional Hugging Face token

    Returns:
        True if download successful
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        logger.info(f"Downloading Dataset to {data_dir} using Python API...")

        # Set token if provided
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token

        # Download specific files from the dataset
        # Files from Hugging Face have .tsv000 extension and need to be renamed to .tsv
        from huggingface_hub import hf_hub_download

        file_mapping = {
            "colors.tsv000": "colors.tsv",
            "keywords.tsv000": "keywords.tsv",
            "photos.tsv000": "photos.tsv",
            "collections.tsv000": "collections.tsv"
        }

        for source_file, target_file in file_mapping.items():
            logger.info(f"Downloading {source_file}...")
            downloaded_path = hf_hub_download(
                repo_id="image-search-2/unsplash_lite_image_dataset",
                repo_type="dataset",
                filename=source_file,
                local_dir=str(data_dir),
                local_dir_use_symlinks=False
            )
            target_path = data_dir / target_file
            if downloaded_path != str(target_path):
                import shutil
                shutil.move(downloaded_path, target_path)
                logger.info(f"Renamed {source_file} to {target_file}")

        logger.info("Dataset download complete")
        return True
    except ImportError:
        logger.warning("huggingface_hub not available, trying CLI approach...")
        if not check_huggingface_cli():
            logger.info("huggingface-cli not found, installing...")
            if not install_huggingface_cli():
                return False

        cmd = [
            "huggingface-cli", "download",
            "image-search-2/unsplash_lite_image_dataset",
            "colors.tsv", "keywords.tsv", "photos.tsv", "collections.tsv",
            "--repo-type", "dataset",
            "--local-dir", str(data_dir),
            "--local-dir-use-symlinks", "False"
        ]

        if hf_token:
            os.environ["HF_TOKEN"] = hf_token

        try:
            logger.info(f"Downloading Dataset to {data_dir}...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Dataset download complete")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Download failed: {e.stderr}")
            return False
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def build_fingerprints(data_dir: Path) -> bool:
    """
    Build fingerprints from downloaded TSV files.

    Args:
        data_dir: Directory containing TSV files

    Returns:
        True if build successful
    """
    # Resolve script path relative to this file's location
    script_path = Path(__file__).resolve().parent.parent / "backend" / "scripts" / "build_unsplash_fingerprints.py"

    if not script_path.exists():
        logger.error(f"Script not found at {script_path}")
        return False

    colors_file = data_dir / "colors.tsv"
    keywords_file = data_dir / "keywords.tsv"
    photos_file = data_dir / "photos.tsv"
    collections_file = data_dir / "collections.tsv"

    if not colors_file.exists():
        colors_file = data_dir / "colors.tsv000"
    if not keywords_file.exists():
        keywords_file = data_dir / "keywords.tsv000"
    if not photos_file.exists():
        photos_file = data_dir / "photos.tsv000"
    if not collections_file.exists():
        collections_file = data_dir / "collections.tsv000"

    cmd = [
        sys.executable, str(script_path),
        "--colors", str(colors_file),
        "--keywords", str(keywords_file),
        "--photos", str(photos_file),
        "--collections", str(collections_file),
        "--batch-size", "1000"
    ]

    try:
        logger.info("Building fingerprints database...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Fingerprints database built successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Build failed: {e.stderr}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        return False


def setup_fingerprints_if_enabled(
    auto_download: bool = False,
    data_dir: Optional[Path] = None,
    hf_token: Optional[str] = None
) -> bool:
    """
    Setup fingerprints if enabled via environment variable or parameter.

    This function can be called during installation to optionally
    download and build the fingerprint database.

    Args:
        auto_download: If True, automatically download Dataset
        data_dir: Directory for TSV files (default: project_root/data/unsplash-dataset)
        hf_token: Optional Hugging Face token

    Returns:
        True if setup successful or skipped
    """
    # Check if enabled via environment variable
    enabled = os.getenv("UNSPLASH_FINGERPRINTS_ENABLED", "false").lower() == "true"

    if not enabled and not auto_download:
        logger.info("Unsplash fingerprints setup skipped (set UNSPLASH_FINGERPRINTS_ENABLED=true to enable)")
        return True

    # Determine data directory
    if data_dir is None:
        # Resolve absolute path to ensure it works from any directory
        project_root = Path(__file__).resolve().parent.parent
        data_dir = project_root / "data" / "unsplash-dataset"

    # Download Dataset
    if not download_dataset(data_dir, hf_token):
        logger.warning("Dataset download failed, skipping fingerprint setup")
        return False

    # Verify files exist
    required_files = ["colors.tsv", "keywords.tsv", "photos.tsv"]
    missing_files = [f for f in required_files if not (data_dir / f).exists()]
    if missing_files:
        logger.error(f"Missing required files: {missing_files}")
        return False

    return build_fingerprints(data_dir)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Setup Unsplash Dataset fingerprints")
    parser.add_argument(
        "--auto-download",
        action="store_true",
        help="Automatically download Dataset from Hugging Face"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Directory for TSV files (default: project_root/data/unsplash-dataset)"
    )
    parser.add_argument(
        "--hf-token",
        help="Hugging Face token (or set HF_TOKEN env var)"
    )

    args = parser.parse_args()

    success = setup_fingerprints_if_enabled(
        auto_download=args.auto_download,
        data_dir=args.data_dir,
        hf_token=args.hf_token or os.getenv("HF_TOKEN")
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

