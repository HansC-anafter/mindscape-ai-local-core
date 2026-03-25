#!/usr/bin/env python3
"""
Shared helpers for the optional Layer Asset Forge host runtime.

These helpers intentionally use only the Python standard library so they can
run on a clean host machine before any pack-specific dependencies are installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

IMPORT_NAME_ALIASES = {
    "opencv-python": "cv2",
    "segment-anything-2": ["sam2", "segment_anything_2"],
    "modnet": ["modnet", "src.models.modnet"],
    "lama-cleaner": "lama_cleaner",
}

SOURCE_INSTALL_STRATEGIES = {
    "segment-anything-2>=1.0.0": {
        "strategy_kind": "pip_git",
        "pip_args": ["git+https://github.com/facebookresearch/sam2.git"],
        "min_python": "3.10",
        "summary": "透過 Git 原始碼安裝 SAM2 Python runtime。",
        "docs_url": "https://github.com/facebookresearch/sam2",
    },
    "modnet": {
        "strategy_kind": "git_checkout_pth",
        "repo_url": "https://github.com/ZHKKKe/MODNet.git",
        "checkout_dirname": "MODNet",
        "pth_filename": "laf_modnet_source.pth",
        "min_python": "3.9",
        "summary": "透過 Git checkout + .pth 掛載 MODNet 原始碼，供人像 matte refinement lane 使用。",
        "docs_url": "https://github.com/ZHKKKe/MODNet",
    },
}

MANUAL_ONLY_STRATEGIES = {
}

MODEL_WEIGHT_PATTERNS = {
    "sam2": [
        "segmentation/by_pack/layer_asset_forge/sam2_hiera_large/**/*.pt",
        "segmentation/by_pack/layer_asset_forge/sam2_hiera_large/**/*.pth",
        "segmentation/store/**/sam2_hiera_large.pt",
        "layer_asset_forge/sam2_hiera_large/**/*.pt",
        "layer_asset_forge/sam2_hiera_large/**/*.pth",
    ],
    "modnet": [
        "matting/by_pack/layer_asset_forge/modnet_photographic/**/*.ckpt",
        "matting/store/**/modnet_photographic_portrait_matting.ckpt",
        "layer_asset_forge/modnet_photographic/**/*.ckpt",
    ],
    "lama": [
        "inpainting/by_pack/layer_asset_forge/lama_big/**/*.pt",
        "inpainting/store/**/big-lama.pt",
        "layer_asset_forge/lama_big/**/*.pt",
    ],
}

_REQUIREMENT_SPLIT_RE = re.compile(r"[<>=!~\[\]\s]")
_PROBE_TIMEOUT_SECONDS = 60
_REMOTE_FETCH_TIMEOUT_SECONDS = int(
    float(os.environ.get("LAF_HOST_RUNTIME_REMOTE_FETCH_TIMEOUT_SECONDS", "120"))
)
_REMOTE_FETCH_RETRIES = max(
    int(float(os.environ.get("LAF_HOST_RUNTIME_REMOTE_FETCH_RETRIES", "3"))),
    1,
)


def default_runtime_root() -> Path:
    configured = os.environ.get("LAF_HOST_RUNTIME_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mindscape" / "runtimes" / "layer_asset_forge"


def default_model_root() -> Path:
    configured = os.environ.get("MINDSCAPE_MODEL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mindscape" / "models"


def preferred_host_python() -> str:
    configured = os.environ.get("LAF_HOST_RUNTIME_BOOTSTRAP_PYTHON", "").strip()
    candidates = [
        configured,
        shutil.which("python3.11") or "",
        shutil.which("python3") or "",
        sys.executable,
    ]
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        candidate_path = Path(normalized).expanduser()
        if candidate_path.exists():
            return str(candidate_path)
        resolved = shutil.which(normalized)
        if resolved:
            return resolved
    return sys.executable


def normalize_requirements(requirements: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for requirement in requirements:
        normalized = str(requirement or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def venv_dir(runtime_root: Path) -> Path:
    return runtime_root / "venv"


def venv_python(runtime_root: Path) -> Path:
    return venv_dir(runtime_root) / "bin" / "python"


def state_file(runtime_root: Path) -> Path:
    return runtime_root / "runtime_state.json"


def is_mock_weight_file(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > 64:
            return False
        return path.read_bytes().startswith(b"MOCK_DATA")
    except Exception:
        return False


def resolve_model_weight_artifact(model_key: str) -> Path:
    normalized = str(model_key or "").strip().lower()
    if normalized in {"segment-anything-2", "sam2_hiera_large"}:
        normalized = "sam2"
    elif normalized in {"modnet_photographic"}:
        normalized = "modnet"
    elif normalized in {"lama_big"}:
        normalized = "lama"

    patterns = MODEL_WEIGHT_PATTERNS.get(normalized, [])
    model_root = default_model_root()
    for pattern in patterns:
        for candidate in sorted(model_root.glob(pattern)):
            if candidate.is_file() and not is_mock_weight_file(candidate):
                return candidate
    raise FileNotFoundError(
        f"Unable to locate real weight artifact for {model_key} under {model_root}"
    )


def fetch_remote_bytes(url: str, *, timeout: int | None = None) -> bytes:
    normalized = str(url or "").strip()
    if not normalized:
        raise ValueError("url is required")
    read_timeout = int(timeout or _REMOTE_FETCH_TIMEOUT_SECONDS)
    last_error: Exception | None = None
    for attempt in range(1, _REMOTE_FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(normalized, timeout=read_timeout) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - exercised via host runtime smoke
            last_error = exc
            if attempt >= _REMOTE_FETCH_RETRIES:
                break
            time.sleep(min(attempt, 3))
    raise RuntimeError(
        f"Failed to fetch remote asset after {_REMOTE_FETCH_RETRIES} attempts: {normalized} ({last_error})"
    )


def venv_site_packages(runtime_root: Path) -> Path:
    lib_root = venv_dir(runtime_root) / "lib"
    candidates = sorted(lib_root.glob("python*/site-packages"))
    if candidates:
        return candidates[0]
    return lib_root / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def parse_python_version(version: str) -> tuple[int, int] | None:
    normalized = str(version or "").strip()
    if not normalized:
        return None
    parts = normalized.split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def detect_python_version(python_executable: Path) -> tuple[int, int] | None:
    if not python_executable.exists():
        return None
    process = subprocess.run(
        [str(python_executable), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    if process.returncode != 0:
        return None
    return parse_python_version(process.stdout.strip())


def required_min_python_for_source_specs(source_specs: Iterable[str]) -> tuple[int, int] | None:
    minimum: tuple[int, int] | None = None
    for spec in normalize_requirements(source_specs):
        strategy = SOURCE_INSTALL_STRATEGIES.get(spec) or {}
        candidate = parse_python_version(str(strategy.get("min_python") or ""))
        if candidate is None:
            continue
        if minimum is None or candidate > minimum:
            minimum = candidate
    return minimum


def base_requirement_name(requirement: str) -> str:
    stripped = str(requirement or "").strip()
    if not stripped:
        return ""
    return _REQUIREMENT_SPLIT_RE.split(stripped, maxsplit=1)[0].strip()


def import_names_for_requirement(requirement: str) -> List[str]:
    base_name = base_requirement_name(requirement)
    if not base_name:
        return []
    alias = IMPORT_NAME_ALIASES.get(base_name, base_name.replace("-", "_"))
    if isinstance(alias, str):
        return [alias]
    if isinstance(alias, (list, tuple, set)):
        return [str(item).strip() for item in alias if str(item).strip()]
    return [base_name.replace("-", "_")]


def _run_python_probe(
    python_executable: Path,
    code: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python_executable), "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
        check=False,
    )


def check_requirement_availability(
    python_executable: Path,
    requirements: Iterable[str],
) -> Dict[str, bool]:
    normalized = normalize_requirements(requirements)
    if not python_executable.exists():
        return {requirement: False for requirement in normalized}

    code = """
import importlib.util
import json
import sys

result = {}
for item in sys.argv[1:]:
    try:
        result[item] = importlib.util.find_spec(item) is not None
    except Exception:
        result[item] = False
sys.stdout.write(json.dumps(result))
""".strip()

    import_name_lists = [import_names_for_requirement(requirement) for requirement in normalized]
    flat_import_names: List[str] = []
    for import_names in import_name_lists:
        for import_name in import_names:
            if import_name not in flat_import_names:
                flat_import_names.append(import_name)
    process = _run_python_probe(python_executable, code, *flat_import_names)
    if process.returncode != 0:
        return {requirement: False for requirement in normalized}

    try:
        discovered = json.loads(process.stdout or "{}")
    except json.JSONDecodeError:
        return {requirement: False for requirement in normalized}

    result: Dict[str, bool] = {}
    for requirement, import_names in zip(normalized, import_name_lists):
        result[requirement] = any(bool(discovered.get(import_name)) for import_name in import_names)
    return result


def detect_torch_backend(python_executable: Path) -> Dict[str, object]:
    if not python_executable.exists():
        return {
            "torch_available": False,
            "torch_backend": None,
            "torch_version": None,
        }

    code = """
import json

payload = {
    "torch_available": False,
    "torch_backend": None,
    "torch_version": None,
}
try:
    import torch

    payload["torch_available"] = True
    payload["torch_version"] = getattr(torch, "__version__", None)
    if torch.cuda.is_available():
        payload["torch_backend"] = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        payload["torch_backend"] = "mps"
    else:
        payload["torch_backend"] = "cpu"
except Exception as exc:
    payload["torch_error"] = str(exc)

print(json.dumps(payload))
""".strip()

    process = _run_python_probe(python_executable, code)
    if process.returncode != 0:
        return {
            "torch_available": False,
            "torch_backend": None,
            "torch_version": None,
            "torch_error": (process.stderr or process.stdout or "").strip(),
        }

    try:
        payload = json.loads(process.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "torch_available": False,
            "torch_backend": None,
            "torch_version": None,
            "torch_error": "invalid_json",
        }

    if not isinstance(payload, dict):
        return {
            "torch_available": False,
            "torch_backend": None,
            "torch_version": None,
            "torch_error": "invalid_payload",
        }
    return payload


def build_install_command(
    runtime_root: Path,
    requirements: Iterable[str],
    *,
    upgrade: bool,
) -> List[str]:
    command = [str(venv_python(runtime_root)), "-m", "pip", "install"]
    if upgrade:
        command.append("--upgrade")
    command.extend(normalize_requirements(requirements))
    return command


def build_source_install_actions(
    runtime_root: Path,
    source_specs: Iterable[str],
    *,
    upgrade: bool,
) -> List[Dict[str, object]]:
    actions: List[Dict[str, object]] = []
    for spec in normalize_requirements(source_specs):
        strategy = SOURCE_INSTALL_STRATEGIES.get(spec) or {}
        pip_args = [
            str(arg).strip()
            for arg in (strategy.get("pip_args") or [])
            if str(arg).strip()
        ]
        command: List[str] = []
        strategy_kind = str(strategy.get("strategy_kind") or "unknown")
        checkout_dir = ""
        pth_path = ""
        command_preview: List[str] = []
        if pip_args:
            command = [str(venv_python(runtime_root)), "-m", "pip", "install"]
            if upgrade:
                command.append("--upgrade")
            command.extend(pip_args)
            command_preview = [" ".join(command)]
        elif strategy_kind == "git_checkout_pth":
            repo_url = str(strategy.get("repo_url") or "").strip()
            checkout_dir = str(
                runtime_root
                / "sources"
                / str(strategy.get("checkout_dirname") or base_requirement_name(spec) or "source")
            )
            pth_path = str(
                venv_site_packages(runtime_root)
                / str(strategy.get("pth_filename") or f"{base_requirement_name(spec)}.pth")
            )
            command_preview = [
                f"git clone --depth 1 {repo_url} {checkout_dir}",
                f"echo {checkout_dir} > {pth_path}",
            ]
        actions.append(
            {
                "install_spec": spec,
                "strategy_kind": strategy_kind,
                "summary": str(strategy.get("summary") or ""),
                "docs_url": str(strategy.get("docs_url") or ""),
                "command": command,
                "command_preview": command_preview,
                "repo_url": str(strategy.get("repo_url") or ""),
                "checkout_dir": checkout_dir,
                "pth_path": pth_path,
            }
        )
    return actions


def build_manual_only_actions(specs: Iterable[str]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    for spec in normalize_requirements(specs):
        strategy = MANUAL_ONLY_STRATEGIES.get(spec) or {}
        actions.append(
            {
                "install_spec": spec,
                "strategy_kind": str(strategy.get("strategy_kind") or "manual_only"),
                "summary": str(strategy.get("summary") or ""),
                "docs_url": str(strategy.get("docs_url") or ""),
            }
        )
    return actions


def execute_source_install_action(
    action: Dict[str, object],
    *,
    timeout_seconds: int = 3600,
) -> Dict[str, object]:
    strategy_kind = str(action.get("strategy_kind") or "unknown")
    if strategy_kind == "pip_git":
        command = [str(part) for part in (action.get("command") or []) if str(part).strip()]
        if not command:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"Missing pip command for source install spec: {action.get('install_spec')}",
                "command_sequence": [],
            }
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "command_sequence": [command],
        }

    if strategy_kind == "git_checkout_pth":
        repo_url = str(action.get("repo_url") or "").strip()
        checkout_dir = Path(str(action.get("checkout_dir") or "")).expanduser()
        pth_path = Path(str(action.get("pth_path") or "")).expanduser()
        if not repo_url or not str(checkout_dir):
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"Missing checkout metadata for source install spec: {action.get('install_spec')}",
                "command_sequence": [],
            }
        git_bin = shutil.which("git")
        if not git_bin:
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": "git is required for MODNet source install but was not found on host.",
                "command_sequence": [],
            }

        command_sequence: List[List[str]] = []
        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        checkout_dir.parent.mkdir(parents=True, exist_ok=True)
        if (checkout_dir / ".git").exists():
            command = [git_bin, "-C", str(checkout_dir), "pull", "--ff-only"]
        elif checkout_dir.exists():
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"Checkout directory exists but is not a git repo: {checkout_dir}",
                "command_sequence": [],
            }
        else:
            command = [git_bin, "clone", "--depth", "1", repo_url, str(checkout_dir)]

        command_sequence.append(command)
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        stdout_chunks.append(process.stdout)
        stderr_chunks.append(process.stderr)
        if process.returncode != 0:
            return {
                "returncode": process.returncode,
                "stdout": "\n".join(chunk for chunk in stdout_chunks if chunk),
                "stderr": "\n".join(chunk for chunk in stderr_chunks if chunk),
                "command_sequence": command_sequence,
            }

        pth_path.parent.mkdir(parents=True, exist_ok=True)
        pth_path.write_text(f"{checkout_dir}\n", encoding="utf-8")
        command_sequence.append(["write_pth", str(pth_path), str(checkout_dir)])
        stdout_chunks.append(f"Wrote {pth_path} -> {checkout_dir}")
        return {
            "returncode": 0,
            "stdout": "\n".join(chunk for chunk in stdout_chunks if chunk),
            "stderr": "\n".join(chunk for chunk in stderr_chunks if chunk),
            "command_sequence": command_sequence,
        }

    return {
        "returncode": 1,
        "stdout": "",
        "stderr": f"Unsupported source install strategy: {strategy_kind}",
        "command_sequence": [],
    }


def write_runtime_state(runtime_root: Path, payload: Dict[str, object]) -> Path:
    runtime_root.mkdir(parents=True, exist_ok=True)
    target = state_file(runtime_root)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target
