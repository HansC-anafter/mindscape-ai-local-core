"""Download and URL policy seam for model weights installer."""

import asyncio as _asyncio
import importlib
import logging
import os
import re
import sys
from contextlib import suppress
from typing import Callable, Dict, Optional

import aiohttp as _aiohttp

from .model_weights_installer_types import (
    DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
    DOWNLOAD_READ_TIMEOUT_SECONDS,
    DOWNLOAD_RETRY_ATTEMPTS,
    DOWNLOAD_RETRY_BASE_DELAY_SECONDS,
    DownloadError,
    ModelInfo,
    ModelProvider,
    ModelStatus,
    SourceNotAllowedError,
)

logger = logging.getLogger(f"{__package__}.model_weights_installer")


def _public_model_weights_module():
    module_name = f"{__package__}.model_weights_installer"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    return importlib.import_module(module_name)


def _public_aiohttp_module():
    return getattr(_public_model_weights_module(), "aiohttp", _aiohttp)


def _public_asyncio_module():
    return getattr(_public_model_weights_module(), "asyncio", _asyncio)


class ModelWeightsInstallerDownloadMixin:
    @staticmethod
    def _parse_content_range_total(content_range: Optional[str]) -> Optional[int]:
        """Extract total size from a Content-Range header like 'bytes */205803670'."""
        if not content_range:
            return None
        match = re.match(r"bytes\s+\*/(\d+)$", content_range.strip())
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    async def _download_model(
        self,
        model_info: ModelInfo,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Download model files with role-aware path mapping."""
        model_info.status = ModelStatus.DOWNLOADING
        key = self._get_model_key(model_info.pack_code, model_info.model_id)

        role_subfolder = self.ROLE_MAP.get(model_info.role, model_info.role)
        fingerprint = self._get_model_fingerprint(model_info)

        store_dir = self.cache_root / role_subfolder / "store" / fingerprint
        store_dir.mkdir(parents=True, exist_ok=True)

        view_dir = (
            self.cache_root
            / role_subfolder
            / "by_pack"
            / model_info.pack_code
            / model_info.model_id
        )
        view_dir.parent.mkdir(parents=True, exist_ok=True)

        if model_info.provider == ModelProvider.LOCAL_BUNDLE:
            self._materialize_local_bundle(model_info, store_dir, view_dir)
            if progress_callback:
                progress_callback(1.0)
            self._download_progress[key] = 1.0
            return

        total_size = sum(f.size_bytes for f in model_info.files)
        downloaded_size = 0

        for file_info in model_info.files:
            file_path = store_dir / file_info.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            partial_path = file_path.parent / f"{file_path.name}.partial"

            url = self._get_download_url(model_info, file_info.filename)
            if not url:
                raise DownloadError(f"No download URL for {file_info.filename}")

            if not self._is_url_allowed(url, pack_code=model_info.pack_code):
                raise SourceNotAllowedError(f"Download source not allowed: {url}")

            request_headers: Optional[Dict[str, str]] = None
            if model_info.provider == ModelProvider.HUGGINGFACE:
                try:
                    from backend.app.services.huggingface_auth_resolver import (
                        resolve_huggingface_auth,
                    )

                    hf_auth = resolve_huggingface_auth()
                    headers = hf_auth.authorization_headers()
                    if headers:
                        request_headers = headers
                except Exception as exc:
                    logger.debug(
                        "Failed to resolve Hugging Face auth for %s: %s",
                        model_info.model_id,
                        exc,
                    )

            aiohttp_module = _public_aiohttp_module()
            asyncio_module = _public_asyncio_module()
            timeout = aiohttp_module.ClientTimeout(
                total=None,
                sock_connect=DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
                sock_read=DOWNLOAD_READ_TIMEOUT_SECONDS,
            )
            last_error: Optional[BaseException] = None
            expected_size = int(file_info.size_bytes or 0)
            base_headers = dict(request_headers or {})

            if (
                not partial_path.exists()
                and file_path.exists()
                and expected_size > 0
                and file_path.stat().st_size < expected_size
            ):
                os.replace(file_path, partial_path)

            for attempt in range(1, DOWNLOAD_RETRY_ATTEMPTS + 1):
                try:
                    existing_size = (
                        partial_path.stat().st_size if partial_path.exists() else 0
                    )
                    headers = dict(base_headers)
                    write_mode = "ab" if existing_size > 0 else "wb"
                    remote_size_hint: Optional[int] = None

                    if existing_size > 0:
                        headers["Range"] = f"bytes={existing_size}-"
                        downloaded_size = existing_size
                    else:
                        downloaded_size = 0

                    async with aiohttp_module.ClientSession(
                        headers=headers, timeout=timeout
                    ) as session:
                        async with session.get(url) as response:
                            if existing_size > 0 and response.status == 200:
                                with suppress(FileNotFoundError):
                                    partial_path.unlink()
                                existing_size = 0
                                downloaded_size = 0
                                raise DownloadError(
                                    "Origin ignored HTTP Range resume request; restarting download"
                                )

                            if response.status == 416 and existing_size > 0:
                                remote_size_hint = self._parse_content_range_total(
                                    response.headers.get("Content-Range")
                                )
                                if (
                                    remote_size_hint is not None
                                    and remote_size_hint == existing_size
                                ):
                                    final_size = existing_size
                                else:
                                    raise DownloadError(f"HTTP 416 downloading {url}")
                            elif response.status not in {200, 206}:
                                raise DownloadError(
                                    f"HTTP {response.status} downloading {url}"
                                )

                            if response.status != 416:
                                with open(partial_path, write_mode) as f:
                                    async for chunk in response.content.iter_chunked(
                                        8192
                                    ):
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        if progress_callback:
                                            progress = (
                                                downloaded_size / total_size
                                                if total_size > 0
                                                else 0
                                            )
                                            progress_callback(progress)
                                            self._download_progress[key] = progress

                    final_size = (
                        partial_path.stat().st_size if partial_path.exists() else 0
                    )
                    effective_expected_size = remote_size_hint or expected_size
                    if effective_expected_size > 0 and final_size < effective_expected_size:
                        raise DownloadError(
                            f"Incomplete download for {file_info.filename}: "
                            f"{final_size}/{effective_expected_size} bytes"
                        )

                    if file_path.exists():
                        file_path.unlink()
                    os.replace(partial_path, file_path)
                    file_info.local_path = file_path
                    file_info.is_downloaded = True
                    break

                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Download attempt %s/%s failed for %s (%s): %r",
                        attempt,
                        DOWNLOAD_RETRY_ATTEMPTS,
                        file_info.filename,
                        type(e).__name__,
                        e,
                    )
                    if attempt >= DOWNLOAD_RETRY_ATTEMPTS:
                        with suppress(FileNotFoundError):
                            partial_path.unlink()
                        model_info.status = ModelStatus.NOT_DOWNLOADED
                        detail = f"{type(e).__name__}: {e!r}"
                        raise DownloadError(
                            f"Failed to download {file_info.filename}: {detail}"
                        ) from e
                    await asyncio_module.sleep(
                        DOWNLOAD_RETRY_BASE_DELAY_SECONDS * attempt
                    )
                    continue

            if last_error is not None and not file_info.is_downloaded:
                model_info.status = ModelStatus.NOT_DOWNLOADED
                detail = f"{type(last_error).__name__}: {last_error!r}"
                raise DownloadError(
                    f"Failed to download {file_info.filename}: {detail}"
                ) from last_error

        self._publish_model_view(model_info, store_dir, view_dir)

    def _get_download_url(self, model_info: ModelInfo, filename: str) -> Optional[str]:
        """Get download URL for a file."""
        if model_info.provider == ModelProvider.HUGGINGFACE:
            repo_id = model_info.repo_id
            revision = model_info.revision or "main"
            return f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"

        elif model_info.provider == ModelProvider.DIRECT_URL:
            if model_info.download_urls:
                for url in model_info.download_urls:
                    if url.endswith(filename):
                        return url
                return model_info.download_urls[0]

        elif model_info.provider == ModelProvider.OSS:
            logger.warning(
                f"OSS provider download not yet implemented for {model_info.model_id}"
            )
            return None

        elif model_info.provider == ModelProvider.LOCAL_BUNDLE:
            logger.info(
                f"Model {model_info.model_id} is a local bundle, no download needed."
            )
            return None

        return None

    def _is_url_allowed(self, url: str, pack_code: Optional[str] = None) -> bool:
        """Check if URL host is in allowlist."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        pack_manifest = self._manifests.get(pack_code, {})
        pack_allowlist = pack_manifest.get("download_policy", {}).get(
            "source_allowlist", []
        )
        effective_allowlist = self._resolve_allowlist(pack_allowlist)

        return parsed.netloc in effective_allowlist
