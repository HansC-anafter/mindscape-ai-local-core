import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Mapping


PREFLIGHT_CONTRACT_PATH = Path("/tmp/mindscape_backend_preflight_contract.json")
PREFLIGHT_CONTRACT_TTL_SECONDS = 120

_DB_FINGERPRINT_KEYS = (
    "DATABASE_URL",
    "DATABASE_URL_CORE",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_CORE_HOST",
    "POSTGRES_CORE_PORT",
    "POSTGRES_CORE_USER",
    "POSTGRES_CORE_DB",
    "POSTGRES_VECTOR_DB",
)


def new_startup_boot_id() -> str:
    return uuid.uuid4().hex[:12]


def compute_db_fingerprint() -> str:
    payload = {key: os.getenv(key, "") for key in _DB_FINGERPRINT_KEYS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _emit(logger: Any, message: str) -> None:
    if hasattr(logger, "info"):
        logger.info(message)
        return
    if callable(logger):
        logger(message)


def capture_phase_duration(
    label: str,
    start_monotonic: float,
    logger: Any,
    *,
    extra: Mapping[str, Any] | None = None,
) -> int:
    duration_ms = int((time.monotonic() - start_monotonic) * 1000)
    extra_text = ""
    if extra:
        extra_text = " " + " ".join(f"{key}={value}" for key, value in extra.items())
    _emit(logger, f"[startup-phase] label={label} duration_ms={duration_ms}{extra_text}")
    return duration_ms


def write_preflight_contract(
    contract: Mapping[str, Any],
    *,
    path: Path = PREFLIGHT_CONTRACT_PATH,
) -> Path:
    path.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_preflight_contract(
    *,
    path: Path = PREFLIGHT_CONTRACT_PATH,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_preflight_contract(*, path: Path = PREFLIGHT_CONTRACT_PATH) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        return


def is_contract_trustworthy(
    contract: Mapping[str, Any] | None,
    *,
    current_db_fingerprint: str | None = None,
    now_epoch: float | None = None,
    ttl_seconds: int = PREFLIGHT_CONTRACT_TTL_SECONDS,
) -> tuple[bool, str]:
    if not contract:
        return False, "missing"
    if now_epoch is None:
        now_epoch = time.time()
    written_at = contract.get("written_at")
    if not isinstance(written_at, (int, float)):
        return False, "missing_written_at"
    if now_epoch - float(written_at) > ttl_seconds:
        return False, "stale"
    if current_db_fingerprint is not None:
        if contract.get("db_fingerprint") != current_db_fingerprint:
            return False, "fingerprint_mismatch"
    if not contract.get("critical_tables_ok"):
        return False, "critical_tables_not_verified"
    if not contract.get("db_ok"):
        return False, "db_not_verified"
    return True, "trusted"
