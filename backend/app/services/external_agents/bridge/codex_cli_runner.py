import asyncio
import functools
import hashlib
import os
import re
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


MAX_CLI_OUTPUT_SIZE = 100_000
DEFAULT_CLI_STALL_TIMEOUT_SECONDS = 180.0
CODEX_APP_BUNDLE_BINARY = "/Applications/Codex.app/Contents/Resources/codex"
_CODEX_CLI_VERSION_RE = re.compile(
    r"codex-cli\s+(\d+)\.(\d+)\.(\d+)(?:[-+.]?([0-9A-Za-z.-]+))?",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class CodexCliProcessResult:
    returncode: int
    stdout_text: str
    stderr_text: str
    output_text: str
    combined_output: str
    synthesized_error: Optional[str] = None


def resolve_codex_cli_cwd(preferred_cwd: Optional[str] = None) -> str:
    candidates = [
        preferred_cwd,
        os.environ.get("HOST_PROJECT_PATH"),
        str(Path(__file__).resolve().parents[5]),
        os.getcwd(),
    ]
    seen: set[str] = set()
    for raw_candidate in candidates:
        candidate = str(raw_candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.getcwd()


def _resolve_codex_cli_candidate(raw_candidate: Optional[str]) -> Optional[str]:
    candidate = str(raw_candidate or "").strip()
    if not candidate:
        return None
    if os.path.isabs(candidate) and os.path.isfile(candidate):
        return candidate
    discovered = shutil.which(candidate)
    if discovered:
        return discovered
    return None


@functools.lru_cache(maxsize=16)
def get_codex_cli_version_sort_key(binary_path: str) -> Tuple[int, int, int, int, str]:
    candidate = str(binary_path or "").strip()
    if not candidate:
        return (-1, -1, -1, -1, "")
    try:
        completed = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return (-1, -1, -1, -1, "")

    version_text = "\n".join(
        part for part in (completed.stdout, completed.stderr) if part
    )
    match = _CODEX_CLI_VERSION_RE.search(version_text)
    if not match:
        return (-1, -1, -1, -1, "")
    prerelease = str(match.group(4) or "").strip()
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        0 if prerelease else 1,
        prerelease,
    )


def _iter_auto_codex_cli_candidates() -> List[str]:
    backend_bundled_binary = (
        Path(__file__).resolve().parents[4]
        / ".runtime-bundles"
        / "codex-cli"
        / "bin"
        / "codex.js"
    )
    repo_bundled_binary = (
        Path(__file__).resolve().parents[5]
        / ".runtime-bundles"
        / "codex-cli"
        / "bin"
        / "codex.js"
    )
    seen: set[str] = set()
    resolved: List[str] = []
    for raw_candidate in (
        CODEX_APP_BUNDLE_BINARY,
        "codex",
        str(backend_bundled_binary),
        str(repo_bundled_binary),
    ):
        candidate = _resolve_codex_cli_candidate(raw_candidate)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        resolved.append(candidate)
    return resolved


def _select_best_codex_cli_candidate(candidates: List[str]) -> Optional[str]:
    if not candidates:
        return None
    ranked: List[Tuple[Tuple[int, int, int, int, str], int, str]] = []
    for index, candidate in enumerate(candidates):
        ranked.append((get_codex_cli_version_sort_key(candidate), -index, candidate))
    return max(ranked)[2]


def resolve_codex_cli_binary(preferred_binary: Optional[str] = None) -> str:
    for raw_candidate in (
        preferred_binary,
        os.environ.get("CODEX_CLI_PATH"),
    ):
        resolved = _resolve_codex_cli_candidate(raw_candidate)
        if resolved:
            return resolved

    auto_candidate = _select_best_codex_cli_candidate(_iter_auto_codex_cli_candidates())
    if auto_candidate:
        return auto_candidate
    return str(preferred_binary or os.environ.get("CODEX_CLI_PATH") or "codex").strip() or "codex"


def looks_like_codex_quota_exhaustion(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "usage limit",
            "rate limit",
            "quota",
            "too many requests",
            "resource_exhausted",
            "429",
        )
    )


def looks_like_codex_auth_failure(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    markers = (
        "401 unauthorized",
        "unauthorized",
        "missing bearer",
        "missing bearer or basic authentication",
        "authentication failed",
        "invalid api key",
        "incorrect api key",
        "missing api key",
        "deactivated_workspace",
        'code":"deactivated_workspace"',
    )
    return any(marker in normalized for marker in markers) and not looks_like_codex_quota_exhaustion(
        normalized
    )


def should_retry_codex_runtime_fault(message: str) -> bool:
    normalized = str(message or "").strip().lower()
    if not normalized:
        return False
    if looks_like_codex_quota_exhaustion(normalized):
        return True
    if looks_like_codex_auth_failure(normalized):
        return True
    if "subprocess stalled after" in normalized:
        return True
    return "no such file or directory (os error 2)" in normalized


def looks_like_codex_transcript(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    prompt_markers = (
        "[Meeting Agent Turn]",
        "[System Prompt]",
        "[Turn Prompt]",
    )
    return sum(marker in normalized for marker in prompt_markers) >= 2


def sanitize_codex_last_message(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    if looks_like_codex_transcript(normalized):
        return ""
    if looks_like_codex_quota_exhaustion(normalized):
        return ""
    if looks_like_codex_auth_failure(normalized):
        return ""
    return normalized


def extract_codex_cli_error(*, stdout: str, stderr: str) -> Optional[str]:
    for source in (stderr, stdout):
        if not source:
            continue
        matches = re.findall(
            r"(?:^|\n)(?:\[[^\n]*\]\s*)?ERROR:\s*(.+)",
            source,
            flags=re.MULTILINE,
        )
        if matches:
            return matches[-1].strip()
    return None


def read_sanitized_codex_last_message(last_message_path: Optional[str]) -> str:
    if not last_message_path or not os.path.isfile(last_message_path):
        return ""
    try:
        return sanitize_codex_last_message(
            Path(last_message_path).read_text(encoding="utf-8")
        )
    except OSError:
        return ""


def resolve_codex_cli_output(
    *,
    stdout: str,
    stderr: str,
    last_message_path: Optional[str],
) -> Tuple[str, Optional[str]]:
    last_message = read_sanitized_codex_last_message(last_message_path)
    if last_message:
        return last_message, None

    transcript_only = "OpenAI Codex v" in stdout and "User instructions:" in stdout
    no_last_message = "no last agent message" in stderr.lower()
    codex_error = extract_codex_cli_error(stdout=stdout, stderr=stderr)

    if codex_error:
        return "", codex_error
    if no_last_message or transcript_only:
        detail = "Codex CLI completed without producing a final agent message"
        if stderr:
            detail = f"{detail}; {stderr[:400]}"
        return "", detail

    output = stdout or stderr
    return output, None


def cli_activity_signature(
    *,
    last_message_path: Optional[str],
    snapshot_root: str,
    snapshot_paths: Optional[List[str]],
) -> Tuple[Tuple[str, int, int], ...]:
    observed: List[Tuple[str, int, int]] = []

    def _record(path: Path) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        observed.append((str(path), int(stat.st_size), int(stat.st_mtime_ns)))

    def _record_last_message(path: Path) -> None:
        try:
            payload = path.read_bytes()
        except OSError:
            return
        if not payload:
            return
        digest = hashlib.sha1(payload).hexdigest()[:16]
        observed.append((str(path), len(payload), int(digest, 16)))

    if last_message_path:
        candidate = Path(last_message_path)
        if candidate.is_file():
            _record_last_message(candidate)

    root_path = Path(snapshot_root) if snapshot_root else None
    if root_path and root_path.is_dir() and isinstance(snapshot_paths, list):
        seen_paths: set[str] = set()
        for raw_path in snapshot_paths:
            if not isinstance(raw_path, str):
                continue
            normalized = raw_path.replace("\\", "/").lstrip("./")
            filename = os.path.basename(normalized)
            for probe in (normalized, filename):
                if not probe:
                    continue
                candidate = root_path / probe
                candidate_str = str(candidate)
                if candidate_str in seen_paths or not candidate.is_file():
                    continue
                _record(candidate)
                seen_paths.add(candidate_str)
                break

    observed.sort()
    return tuple(observed)


async def _terminate_cli_process(
    *,
    proc: asyncio.subprocess.Process,
    communicate_task: Optional[asyncio.Task[Tuple[bytes, bytes]]] = None,
    wait_timeout: float = 5.0,
) -> None:
    bounded_wait = max(0.5, float(wait_timeout))
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.kill()

    if communicate_task is not None and not communicate_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(communicate_task), timeout=bounded_wait)
            return
        except asyncio.TimeoutError:
            communicate_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await communicate_task

    if proc.returncode is None:
        with suppress(asyncio.TimeoutError, ProcessLookupError):
            await asyncio.wait_for(proc.wait(), timeout=bounded_wait)


async def wait_for_cli_subprocess_activity(
    *,
    proc: asyncio.subprocess.Process,
    runtime_name: str,
    execution_id: str,
    last_message_path: Optional[str],
    snapshot_root: str,
    snapshot_paths: Optional[List[str]],
    stall_timeout: Optional[float],
) -> Tuple[bytes, bytes]:
    communicate_task = asyncio.create_task(proc.communicate())
    try:
        if not stall_timeout or stall_timeout <= 0:
            return await communicate_task

        poll_interval = min(5.0, max(0.5, stall_timeout / 6.0))
        last_activity_at = asyncio.get_running_loop().time()
        last_activity = cli_activity_signature(
            last_message_path=last_message_path,
            snapshot_root=snapshot_root,
            snapshot_paths=snapshot_paths,
        )

        while True:
            done, _ = await asyncio.wait({communicate_task}, timeout=poll_interval)
            if communicate_task in done:
                return await communicate_task

            current_activity = cli_activity_signature(
                last_message_path=last_message_path,
                snapshot_root=snapshot_root,
                snapshot_paths=snapshot_paths,
            )
            if current_activity != last_activity:
                last_activity = current_activity
                last_activity_at = asyncio.get_running_loop().time()
                continue

            if asyncio.get_running_loop().time() - last_activity_at < stall_timeout:
                continue

            await _terminate_cli_process(
                proc=proc,
                communicate_task=communicate_task,
                wait_timeout=poll_interval,
            )
            raise asyncio.TimeoutError(
                f"{runtime_name} subprocess stalled after {int(stall_timeout)}s without file or message activity ({execution_id})"
            )
    except asyncio.CancelledError:
        await _terminate_cli_process(
            proc=proc,
            communicate_task=communicate_task,
        )
        raise


async def run_codex_cli_subprocess(
    *,
    cmd: List[str],
    cwd: str,
    env: Dict[str, str],
    last_message_path: str,
    execution_id: str,
    timeout: float,
    stall_timeout: Optional[float],
    snapshot_root: str = "",
    snapshot_paths: Optional[List[str]] = None,
    max_output_size: int = MAX_CLI_OUTPUT_SIZE,
) -> CodexCliProcessResult:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            wait_for_cli_subprocess_activity(
                proc=proc,
                runtime_name="codex_cli",
                execution_id=execution_id,
                last_message_path=last_message_path,
                snapshot_root=snapshot_root,
                snapshot_paths=snapshot_paths,
                stall_timeout=stall_timeout,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        salvaged_output = read_sanitized_codex_last_message(last_message_path)
        if salvaged_output:
            if proc.returncode is None:
                await _terminate_cli_process(proc=proc)
            return CodexCliProcessResult(
                returncode=0,
                stdout_text="",
                stderr_text="",
                output_text=salvaged_output,
                combined_output=salvaged_output,
            )
        if proc.returncode is None:
            await _terminate_cli_process(proc=proc)
        raise
    except Exception:
        if proc.returncode is None:
            await _terminate_cli_process(proc=proc)
        raise

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")[:max_output_size].strip()
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")[:max_output_size].strip()
    output_text, synthesized_error = resolve_codex_cli_output(
        stdout=stdout_text,
        stderr=stderr_text,
        last_message_path=last_message_path,
    )
    combined_output = "\n".join(
        part for part in (output_text, stdout_text, stderr_text) if part
    ).strip()
    return CodexCliProcessResult(
        returncode=proc.returncode,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        output_text=output_text,
        combined_output=combined_output,
        synthesized_error=synthesized_error,
    )
