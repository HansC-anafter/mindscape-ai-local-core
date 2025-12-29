"""
Pack Download Service

Handles downloading capability packs from remote cloud providers.
Downloads pack files (.mindpack) and validates checksums.

This is a neutral service that works with any CloudProvider implementation.
"""

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import httpx
except ImportError:
    httpx = None

from backend.app.services.cloud_providers.base import CloudProvider

logger = logging.getLogger(__name__)


class PackDownloadService:
    """Service for downloading capability packs from cloud providers"""

    def __init__(self):
        """Initialize pack download service"""
        if not httpx:
            logger.warning("httpx not installed, pack download features will be disabled")
            self._httpx_available = False
        else:
            self._httpx_available = True

    async def download_pack(
        self,
        provider: CloudProvider,
        pack_ref: str,
        verify_checksum: bool = True
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Download a pack from a cloud provider

        Args:
            provider: CloudProvider instance (must have get_download_link method)
            pack_ref: Pack reference in format "provider_id:code@version"
            verify_checksum: Whether to verify SHA256 checksum

        Returns:
            Tuple of (success: bool, pack_file_path: Optional[Path], error_message: Optional[str])
        """
        if not self._httpx_available:
            return False, None, "httpx not available"

        try:
            # 1. Get download link from provider
            logger.info(f"Getting download link for pack: {pack_ref}")
            download_info = await provider.get_download_link(pack_ref)

            download_url = download_info.get("download_url")
            if not download_url:
                return False, None, "Download URL not found in response"

            expected_checksum = download_info.get("checksum")
            expected_size = download_info.get("size")

            # 2. Download pack file
            logger.info(f"Downloading pack from: {download_url}")
            pack_file = await self._download_file(download_url, expected_size)

            # 3. Verify checksum if provided
            if verify_checksum and expected_checksum:
                logger.info(f"Verifying checksum for pack: {pack_ref}")
                if not self._verify_checksum(pack_file, expected_checksum):
                    pack_file.unlink()
                    return False, None, f"Checksum verification failed for pack {pack_ref}"

            logger.info(f"Successfully downloaded pack: {pack_ref}")
            return True, pack_file, None

        except ValueError as e:
            # Authentication or access denied errors
            logger.error(f"Access error downloading pack {pack_ref}: {e}")
            return False, None, str(e)
        except Exception as e:
            logger.error(f"Failed to download pack {pack_ref}: {e}", exc_info=True)
            return False, None, f"Download failed: {str(e)}"

    async def _download_file(
        self,
        download_url: str,
        expected_size: Optional[int] = None
    ) -> Path:
        """
        Download file from URL to temporary location

        Args:
            download_url: URL to download from
            expected_size: Expected file size in bytes (optional, for validation)

        Returns:
            Path to downloaded file

        Raises:
            Exception: If download fails
        """
        if not self._httpx_available:
            raise Exception("httpx not available")

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mindpack')
        temp_path = Path(temp_file.name)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout for large files
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()

                    # Check content length if provided
                    content_length = response.headers.get("content-length")
                    if content_length and expected_size:
                        actual_size = int(content_length)
                        if actual_size != expected_size:
                            logger.warning(
                                f"Size mismatch: expected {expected_size}, got {actual_size}"
                            )

                    # Download file
                    downloaded_size = 0
                    async for chunk in response.aiter_bytes():
                        temp_file.write(chunk)
                        downloaded_size += len(chunk)

                    temp_file.close()

                    # Verify downloaded size
                    if expected_size and downloaded_size != expected_size:
                        logger.warning(
                            f"Downloaded size mismatch: expected {expected_size}, "
                            f"got {downloaded_size}"
                        )

                    logger.info(f"Downloaded {downloaded_size} bytes to {temp_path}")
                    return temp_path

        except httpx.TimeoutException:
            if temp_path.exists():
                temp_path.unlink()
            raise Exception("Download timeout")
        except httpx.HTTPStatusError as e:
            if temp_path.exists():
                temp_path.unlink()
            raise Exception(f"HTTP error: {e.response.status_code}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """
        Verify SHA256 checksum of downloaded file

        Args:
            file_path: Path to file
            expected_checksum: Expected checksum in format "sha256:..." or just hex string

        Returns:
            True if checksum matches, False otherwise
        """
        try:
            # Remove "sha256:" prefix if present
            if expected_checksum.startswith("sha256:"):
                expected_hex = expected_checksum[7:]
            else:
                expected_hex = expected_checksum

            # Calculate actual checksum
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)

            actual_hex = sha256_hash.hexdigest()

            # Compare (case-insensitive)
            matches = actual_hex.lower() == expected_hex.lower()

            if not matches:
                logger.warning(
                    f"Checksum mismatch: expected {expected_hex[:16]}..., "
                    f"got {actual_hex[:16]}..."
                )

            return matches

        except Exception as e:
            logger.error(f"Error verifying checksum: {e}")
            return False


def get_pack_download_service() -> PackDownloadService:
    """Get PackDownloadService instance"""
    return PackDownloadService()

