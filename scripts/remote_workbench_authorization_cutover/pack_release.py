"""Known-good artifact capture, durable install, and exact restore gates."""
from __future__ import annotations
import base64
import hashlib
import json
import re
import sys
import tarfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import yaml
from .http import HttpClient
from .install_receipt import next_restore_attempt_round, write_install_attempt
from .install_state import AcceptedInstallError
from .io import (
    CommandExecutor,
    CutoverError,
    assert_private_file,
    write_private_json,
)
CAPABILITY_CODE = "mindscape_cloud_integration"
ACTIVE_INSTALL_STATES = (
    "queued",
    "running",
    "waiting_db",
    "pending_execution_activation",
)
INSTALL_POLL_BUDGET_SECONDS = 600.0
MAX_PACK_BYTES = 128 * 1024 * 1024
_ARTIFACT_PATH = re.compile(
    r"^/app/data/capability-install-jobs/([a-f0-9]{32})/input\.mindpack$"
)
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_INSTALL_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
class PackReleaseGate:
    """Use the durable file-upload artifact seam for release and backout."""
    def __init__(
        self,
        *,
        cloud_worktree: Path,
        executor: CommandExecutor,
        http: HttpClient,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cloud_worktree = cloud_worktree
        self.executor = executor
        self.http = http
        self.sleep = sleep
        self.monotonic = monotonic
    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    @staticmethod
    def _manifest_bytes(archive: Path) -> bytes:
        expected_suffix = f"{CAPABILITY_CODE}/manifest.yaml"
        try:
            if tarfile.is_tarfile(archive):
                with tarfile.open(archive, "r:*") as handle:
                    names = [name for name in handle.getnames() if name.endswith(expected_suffix)]
                    if len(names) != 1:
                        raise CutoverError("Known-good archive manifest is ambiguous")
                    member = handle.extractfile(names[0])
                    if member is None:
                        raise CutoverError("Known-good archive manifest is unavailable")
                    return member.read(1_048_577)
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive) as handle:
                    names = [name for name in handle.namelist() if name.endswith(expected_suffix)]
                    if len(names) != 1:
                        raise CutoverError("Known-good archive manifest is ambiguous")
                    return handle.read(names[0])
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as error:
            raise CutoverError("Known-good archive cannot be read") from error
        raise CutoverError("Known-good archive format is unsupported")
    @classmethod
    def _verify_archive_manifest(
        cls,
        archive: Path,
        *,
        version: str,
        manifest_hash: str,
    ) -> None:
        raw = cls._manifest_bytes(archive)
        if not raw or len(raw) > 1_048_576:
            raise CutoverError("Known-good manifest exceeds its byte budget")
        if hashlib.sha256(raw).hexdigest() != manifest_hash:
            raise CutoverError("Known-good manifest hash does not match activation")
        try:
            manifest = yaml.safe_load(raw)
        except yaml.YAMLError as error:
            raise CutoverError("Known-good manifest is malformed") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("code") != CAPABILITY_CODE
            or str(manifest.get("version") or "") != version
        ):
            raise CutoverError("Known-good manifest identity does not match runtime")
    def _runtime_identity(self) -> tuple[str, str]:
        base = "http://localhost:8200/api/v1/capability-packs"
        metadata = self.http.get_json(
            f"{base}/installed-capabilities/{CAPABILITY_CODE}",
            timeout_seconds=10.0,
        )
        active = self.http.get_json(
            f"{base}/{CAPABILITY_CODE}/activation",
            timeout_seconds=10.0,
        )
        version = str(metadata.get("version") or "")
        manifest_hash = str(active.get("manifest_hash") or "")
        if (
            metadata.get("id") != CAPABILITY_CODE
            or metadata.get("code") != CAPABILITY_CODE
            or not _VERSION_PATTERN.fullmatch(version)
            or active.get("pack_id") != CAPABILITY_CODE
            or active.get("enabled") is not True
            or active.get("activation_state") != "active"
            or not _HASH_PATTERN.fullmatch(manifest_hash)
        ):
            raise CutoverError("Installed capability identity is incomplete")
        return version, manifest_hash
    def capture_known_good(self, secure_dir: Path) -> dict[str, Any]:
        """Copy the exact current file-upload job artifact before any install."""
        version, manifest_hash = self._runtime_identity()
        sql = """
SELECT json_build_object(
  'install_id', install_id,
  'source_kind', source_kind,
  'source_path', source_payload->>'mindpack_path',
  'version', result_payload->>'version',
  'manifest_hash', result_payload->'activation'->>'manifest_hash'
)::text
FROM capability_install_jobs
WHERE state = 'succeeded'
  AND source_kind = 'file_upload'
  AND result_payload->>'capability_code' = 'mindscape_cloud_integration'
  AND result_payload->>'version' = :'version'
  AND result_payload->'activation'->>'manifest_hash' = :'manifest_hash'
ORDER BY finished_at DESC
LIMIT 1;
""".strip()
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-XqAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                f"version={version}",
                "-v",
                f"manifest_hash={manifest_hash}",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-c",
                sql,
            ],
            timeout_seconds=20.0,
        ).strip()
        try:
            source = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Known-good install artifact evidence is unavailable") from error
        if not isinstance(source, dict):
            raise CutoverError("Known-good install artifact evidence is malformed")
        source_path = str(source.get("source_path") or "")
        match = _ARTIFACT_PATH.fullmatch(source_path)
        if (
            not match
            or source.get("install_id") != match.group(1)
            or source.get("source_kind") != "file_upload"
            or source.get("version") != version
            or source.get("manifest_hash") != manifest_hash
        ):
            raise CutoverError("Known-good artifact is not the current durable file upload")
        archive = secure_dir / f"known-good-{CAPABILITY_CODE}-{version}.mindpack"
        evidence_path = secure_dir / "known-good-pack.json"
        if archive.exists() or evidence_path.exists():
            raise CutoverError("Known-good evidence already exists; run explicit backout first")
        self.executor.run(
            [
                "docker",
                "cp",
                f"mindscape-ai-local-core-backend-control:{source_path}",
                str(archive),
            ],
            timeout_seconds=120.0,
        )
        try:
            archive.chmod(0o600)
        except OSError as error:
            raise CutoverError("Known-good artifact permissions could not be locked") from error
        assert_private_file(archive, max_bytes=MAX_PACK_BYTES)
        self._verify_archive_manifest(
            archive,
            version=version,
            manifest_hash=manifest_hash,
        )
        evidence = {
            "schema_version": 1,
            "capability_code": CAPABILITY_CODE,
            "version": version,
            "manifest_hash": manifest_hash,
            "source_kind": "file_upload",
            "source_install_id": source["install_id"],
            "source_container_path": source_path,
            "archive_file": archive.name,
            "archive_sha256": self._sha256(archive),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        write_private_json(evidence_path, evidence)
        return evidence
    def package_current(self) -> Path:
        """Validate and package only the already repository-locked Cloud source."""
        self.executor.run(
            [
                sys.executable,
                str(self.cloud_worktree / "scripts/validate_manifest.py"),
                CAPABILITY_CODE,
            ],
            timeout_seconds=120.0,
        )
        self.executor.run(
            [
                sys.executable,
                str(self.cloud_worktree / "scripts/package_capability.py"),
                CAPABILITY_CODE,
            ],
            timeout_seconds=600.0,
        )
        archive = self.cloud_worktree / f"{CAPABILITY_CODE}.mindpack"
        listing = self.executor.run(["tar", "tzf", str(archive)], timeout_seconds=60.0)
        required = (
            f"{CAPABILITY_CODE}/manifest.yaml",
            f"{CAPABILITY_CODE}/ui_dist/ui_dist_manifest.json",
        )
        if any(item not in listing.splitlines() for item in required):
            raise CutoverError("Capability archive is missing manifest or runtime UI assets")
        return archive
    def _install_archive(
        self,
        archive: Path,
        *,
        overwrite: bool,
        evidence_dir: Path | None = None,
        attempt_kind: str = "install",
        attempt_round: int = 1,
    ) -> dict[str, Any]:
        command = [
            "curl",
            "-sS",
            "--fail-with-body",
            "-X",
            "POST",
            "http://localhost:8220/api/v1/capability-packs/install-from-file",
            "-F",
            f"file=@{archive}",
        ]
        if overwrite:
            command.extend(
                [
                    "-F",
                    "allow_overwrite=true",
                    "-F",
                    "overwrite_confirmation=OVERWRITE",
                    "-F",
                    "overwrite_review_confirmation=REVIEWED_LOCAL_DIFFS",
                ]
            )
        raw = self.executor.run(command, timeout_seconds=120.0)
        try:
            accepted = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Install intake returned malformed JSON") from error
        if (
            not isinstance(accepted, dict)
            or accepted.get("success") is not True
            or accepted.get("accepted") is not True
        ):
            raise CutoverError("Backend-control did not accept a durable install job")
        install_id = str(accepted.get("install_id") or "")
        status_url = str(accepted.get("status_url") or "")
        state = str(accepted.get("state") or "")
        if (
            not _INSTALL_ID_PATTERN.fullmatch(install_id)
            or status_url != f"/api/v1/capability-packs/install-jobs/{install_id}"
            or state not in ACTIVE_INSTALL_STATES
        ):
            raise CutoverError("Install intake returned an invalid status URL")
        if evidence_dir is not None:
            write_install_attempt(
                evidence_dir,
                attempt_kind=attempt_kind,
                install_id=install_id,
                state=state,
                terminal=False,
                attempt_round=attempt_round,
            )
        url = f"http://localhost:8220{status_url}"
        deadline = self.monotonic() + INSTALL_POLL_BUDGET_SECONDS
        try:
            while self.monotonic() < deadline:
                job = self.http.get_json(url, timeout_seconds=10.0)
                state = str(job.get("state") or "")
                if job.get("install_id") != install_id:
                    raise AcceptedInstallError(
                        "Install status identity changed",
                        install_id=install_id,
                        state=state,
                        terminal=False,
                    )
                if evidence_dir is not None:
                    write_install_attempt(
                        evidence_dir,
                        attempt_kind=attempt_kind,
                        install_id=install_id,
                        state=state,
                        terminal=state in {"succeeded", "failed"},
                        attempt_round=attempt_round,
                    )
                if state == "succeeded":
                    result = job.get("result_payload")
                    activation = (
                        result.get("execution_activation")
                        if isinstance(result, dict)
                        else None
                    )
                    if not isinstance(activation, dict) or activation.get("state") in {
                        None,
                        "pending",
                        "pending_execution_activation",
                    }:
                        raise AcceptedInstallError(
                            "Execution activation remains pending",
                            install_id=install_id,
                            state=state,
                            terminal=True,
                        )
                    try:
                        self.verify_installed_runtime(job)
                    except Exception as error:  # noqa: BLE001 - retain terminal receipt
                        raise AcceptedInstallError(
                            "Installed runtime verification failed",
                            install_id=install_id,
                            state=state,
                            terminal=True,
                        ) from error
                    return job
                if state == "failed":
                    raise AcceptedInstallError(
                        "Capability install job failed",
                        install_id=install_id,
                        state=state,
                        terminal=True,
                    )
                if state not in ACTIVE_INSTALL_STATES:
                    raise AcceptedInstallError(
                        "Capability install job returned an unknown state",
                        install_id=install_id,
                        state=state,
                        terminal=False,
                    )
                self.sleep(min(2.0, max(0.0, deadline - self.monotonic())))
        except AcceptedInstallError:
            raise
        except Exception as error:  # noqa: BLE001 - accepted state is indeterminate
            raise AcceptedInstallError(
                "Accepted capability install state became indeterminate",
                install_id=install_id,
                state=state,
                terminal=False,
            ) from error
        raise AcceptedInstallError(
            "Capability install job exceeded its 600 second poll budget",
            install_id=install_id,
            state=state,
            terminal=False,
        )
    def install_current(self, archive: Path, evidence_dir: Path) -> dict[str, Any]:
        return self._install_archive(
            archive,
            overwrite=False,
            evidence_dir=evidence_dir,
        )
    def restore_known_good(self, secure_dir: Path) -> dict[str, Any]:
        """Reinstall the captured archive only through the 8220 durable job path."""
        evidence_path = secure_dir / "known-good-pack.json"
        assert_private_file(evidence_path, max_bytes=32_768)
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CutoverError("Known-good pack evidence is malformed") from error
        if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
            raise CutoverError("Known-good pack evidence schema is invalid")
        version = str(evidence.get("version") or "")
        manifest_hash = str(evidence.get("manifest_hash") or "")
        archive = secure_dir / str(evidence.get("archive_file") or "")
        if archive.parent != secure_dir or not _VERSION_PATTERN.fullmatch(version):
            raise CutoverError("Known-good pack evidence path or version is invalid")
        assert_private_file(archive, max_bytes=MAX_PACK_BYTES)
        if self._sha256(archive) != evidence.get("archive_sha256"):
            raise CutoverError("Known-good archive sha256 mismatch")
        self._verify_archive_manifest(
            archive,
            version=version,
            manifest_hash=manifest_hash,
        )
        job = self._install_archive(
            archive,
            overwrite=True,
            evidence_dir=secure_dir,
            attempt_kind="restore",
            attempt_round=next_restore_attempt_round(secure_dir),
        )
        result = job.get("result_payload") or {}
        activation = result.get("activation") or {}
        if result.get("version") != version or activation.get("manifest_hash") != manifest_hash:
            raise CutoverError("Known-good restore job identity does not match evidence")
        return job
    def verify_installed_runtime(self, job: dict[str, Any]) -> None:
        """Verify installed source, activation hash, and every runtime UI asset."""
        result = job.get("result_payload")
        if not isinstance(result, dict):
            raise CutoverError("Install job result payload is missing")
        activation = result.get("activation")
        manifest_hash = activation.get("manifest_hash") if isinstance(activation, dict) else None
        version = str(result.get("version") or "").strip()
        if (
            job.get("source_kind") != "file_upload"
            or result.get("success") is not True
            or result.get("capability_code") != CAPABILITY_CODE
            or not _VERSION_PATTERN.fullmatch(version)
            or not isinstance(manifest_hash, str)
            or not _HASH_PATTERN.fullmatch(manifest_hash)
        ):
            raise CutoverError("Installed capability source metadata is incomplete")
        self._verify_runtime_assets(version, manifest_hash)
    def _verify_runtime_assets(self, version: str, manifest_hash: str) -> None:
        base = "http://localhost:8200/api/v1/capability-packs"
        runtime_version, runtime_hash = self._runtime_identity()
        if runtime_version != version or runtime_hash != manifest_hash:
            raise CutoverError("Execution-plane activation does not match installed source")
        response = self.http.request(
            "GET",
            f"{base}/installed-capabilities/{CAPABILITY_CODE}/ui-components",
            timeout_seconds=10.0,
            max_response_bytes=262_144,
        )
        if not 200 <= response.status < 300:
            raise CutoverError("Runtime UI component metadata is unavailable")
        try:
            components = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CutoverError("Runtime UI component metadata is malformed") from error
        if not isinstance(components, list) or not components:
            raise CutoverError("Installed capability has no runtime UI components")
        prefix = f"/api/v1/capability-packs/installed-capabilities/{CAPABILITY_CODE}/ui-assets/"
        for component in components:
            if not isinstance(component, dict):
                raise CutoverError("Runtime UI component entry is malformed")
            asset_url = str(component.get("asset_url") or "")
            integrity = str(component.get("integrity") or "")
            declared_bytes = component.get("bytes")
            if (
                not asset_url.startswith(prefix)
                or not integrity.startswith("sha256-")
                or type(declared_bytes) is not int
                or declared_bytes <= 0
                or not str(component.get("runtime") or "")
            ):
                raise CutoverError("Runtime UI component integrity metadata is incomplete")
            asset = self.http.request(
                "GET",
                f"http://localhost:8200{asset_url}",
                timeout_seconds=20.0,
                max_response_bytes=declared_bytes,
            )
            digest = "sha256-" + base64.b64encode(
                hashlib.sha256(asset.body).digest()
            ).decode("ascii")
            if (
                not 200 <= asset.status < 300
                or len(asset.body) != declared_bytes
                or digest != integrity
            ):
                raise CutoverError("Runtime UI asset bytes failed integrity verification")
