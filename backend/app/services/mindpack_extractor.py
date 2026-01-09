"""
Mindpack Extractor

Extract .mindpack files, check structure, return temporary directory and capability root path.

⚠️ Compatibility layer: Supports both ZIP (new format) and tar.gz (legacy format).
"""

import logging
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def _detect_format(mindpack_path: Path) -> str:
    """
    Detect .mindpack file format

    Args:
        mindpack_path: Path to .mindpack file

    Returns:
        "zip" or "tar.gz"
    """
    # Check file signature
    with open(mindpack_path, "rb") as f:
        header = f.read(4)

    # ZIP signature: PK\x03\x04
    if header[:2] == b"PK":
        return "zip"
    # tar.gz signature: gzip magic number
    elif header[:2] == b"\x1f\x8b":
        return "tar.gz"
    else:
        # Default to tar.gz for backward compatibility
        logger.warning(f"Unknown file format, assuming tar.gz: {mindpack_path}")
        return "tar.gz"


class MindpackExtractor:
    """Extract and validate .mindpack file structure"""

    def __init__(self, local_core_root: Path):
        """
        Initialize extractor

        Args:
            local_core_root: Local-core project root directory
        """
        self.local_core_root = local_core_root

    def extract(
        self, mindpack_path: Path
    ) -> Tuple[bool, Optional[Path], Optional[str], Optional[Path]]:
        """
        Extract .mindpack file to temporary directory

        Supports both ZIP (new format) and tar.gz (legacy format).

        Args:
            mindpack_path: Path to .mindpack file

        Returns:
            (success: bool, temp_dir: Path, capability_code: str, cap_dir: Path)
            Returns (False, None, None, None) on failure
        """
        if not mindpack_path.exists():
            logger.error(f"Mindpack file not found: {mindpack_path}")
            return False, None, None, None

        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"Extracting {mindpack_path} to temporary directory: {temp_dir}")

        # Detect format
        file_format = _detect_format(mindpack_path)
        logger.info(f"Detected mindpack format: {file_format}")

        try:
            if file_format == "zip":
                return self._extract_zip(mindpack_path, temp_dir)
            else:  # tar.gz
                return self._extract_tar_gz(mindpack_path, temp_dir)
        except Exception as e:
            logger.error(f"Failed to extract mindpack: {e}")
            return False, temp_dir, None, None

    def _extract_zip(
        self, mindpack_path: Path, temp_dir: Path
    ) -> Tuple[bool, Optional[Path], Optional[str], Optional[Path]]:
        """
        Extract ZIP format .mindpack

        Format:
        - manifest.yaml at ZIP root
        - capabilities/{capability_code}/ (tools, services, api, playbooks)
        """
        try:
            with zipfile.ZipFile(mindpack_path, "r") as zipf:
                zipf.extractall(temp_dir)

            # Check for manifest.yaml at ZIP root
            manifest_path = temp_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.error("manifest.yaml not found at ZIP root")
                return False, temp_dir, None, None

            # Read manifest to get capability code
            import yaml

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
            capability_code = manifest.get("code")
            if not capability_code:
                logger.error("manifest.yaml missing 'code' field")
                return False, temp_dir, None, None

            # Find capability directory
            capabilities_dir = temp_dir / "capabilities"
            if capabilities_dir.exists():
                cap_dir = capabilities_dir / capability_code
                if cap_dir.exists():
                    logger.info(
                        f"Extracted capability: {capability_code} from {mindpack_path}"
                    )
                    return True, temp_dir, capability_code, cap_dir
                else:
                    logger.warning(
                        f"capabilities/{capability_code}/ not found, using temp_dir as cap_dir"
                    )
                    return True, temp_dir, capability_code, temp_dir
            else:
                logger.warning(
                    "capabilities/ directory not found, using temp_dir as cap_dir"
                )
                cap_dir = temp_dir

            # ⚠️ Blueprint Compliance: Copy manifest.yaml to capability directory
            # Runtime requires /app/capabilities/{code}/manifest.yaml to exist
            if cap_dir != temp_dir:
                import shutil

                dest_manifest = cap_dir / "manifest.yaml"
                if not dest_manifest.exists():
                    logger.info(f"Copying manifest.yaml to {dest_manifest}")
                    shutil.copy2(manifest_path, dest_manifest)

            return True, temp_dir, capability_code, cap_dir

        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            return False, temp_dir, None, None

    def _extract_tar_gz(
        self, mindpack_path: Path, temp_dir: Path
    ) -> Tuple[bool, Optional[Path], Optional[str], Optional[Path]]:
        """
        Extract tar.gz format .mindpack (legacy format)

        Format:
        - {capability_code}/manifest.yaml
        - {capability_code}/ (tools, services, api, playbooks)
        """
        try:
            with tarfile.open(mindpack_path, "r:gz") as tar:
                tar.extractall(temp_dir)

            # Find capability directory in extracted files
            extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
            if not extracted_dirs:
                logger.error("No capability directory found in mindpack")
                return False, temp_dir, None, None

            cap_extracted_dir = extracted_dirs[0]
            capability_code = cap_extracted_dir.name

            # Verify manifest exists
            manifest_path = cap_extracted_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.error("manifest.yaml not found in mindpack")
                return False, temp_dir, capability_code, None

            logger.info(f"Extracted capability: {capability_code} from {mindpack_path}")
            return True, temp_dir, capability_code, cap_extracted_dir

        except tarfile.TarError as e:
            logger.error(f"Invalid tar.gz file: {e}")
            return False, temp_dir, None, None

    def cleanup(self, temp_dir: Optional[Path]):
        """
        Clean up temporary directory

        Args:
            temp_dir: Temporary directory to clean up
        """
        if temp_dir and temp_dir.exists():
            import shutil

            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory: {e}")
