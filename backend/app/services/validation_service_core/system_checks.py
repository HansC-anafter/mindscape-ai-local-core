"""System health checks for validation service."""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


def validate_system_health(
    local_core_root: Path,
    result: Dict,
    capabilities_dir: Path,
    specs_dir: Path,
    i18n_base_dir: Path,
) -> None:
    """Run system health checks and append results to the validation payload."""
    db_ok, db_errors = check_database_connection()
    result["validation_stages"]["database"] = {"ok": db_ok, "errors": db_errors}
    result["errors"].extend(db_errors)

    dir_ok, dir_errors = check_directory_permissions(
        local_core_root, capabilities_dir, specs_dir, i18n_base_dir
    )
    result["validation_stages"]["directories"] = {
        "ok": dir_ok,
        "errors": dir_errors,
    }
    result["errors"].extend(dir_errors)

    services_ok, service_errors, service_warnings = check_dependency_services()
    result["validation_stages"]["services"] = {
        "ok": services_ok,
        "errors": service_errors,
        "warnings": service_warnings,
    }
    result["warnings"].extend(service_warnings)

    disk_ok, disk_errors = check_disk_space(local_core_root)
    result["validation_stages"]["disk_space"] = {
        "ok": disk_ok,
        "errors": disk_errors,
    }
    result["errors"].extend(disk_errors)


def check_database_connection() -> Tuple[bool, List[str]]:
    """Check database connection."""
    errors = []
    try:
        store = PostgresStoreBase()
        with store.get_connection() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        errors.append(f"Database connection failed: {exc}")
    return len(errors) == 0, errors


def check_directory_permissions(
    local_core_root: Path,
    capabilities_dir: Path,
    specs_dir: Path,
    i18n_base_dir: Path,
) -> Tuple[bool, List[str]]:
    """Check directory permissions."""
    errors = []
    directories = [
        capabilities_dir,
        specs_dir,
        i18n_base_dir,
        local_core_root / "web-console" / "src" / "app" / "capabilities",
    ]

    for dir_path in directories:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            test_file = dir_path / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
        except PermissionError:
            errors.append(f"Directory not writable: {dir_path}")
        except Exception as exc:
            errors.append(f"Directory check failed for {dir_path}: {exc}")

    return len(errors) == 0, errors


def check_dependency_services() -> Tuple[bool, List[str], List[str]]:
    """Check dependency services."""
    errors = []
    warnings = []

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis

            redis_client = redis.from_url(redis_url)
            redis_client.ping()
        except ImportError:
            warnings.append("Redis client not installed")
        except Exception as exc:
            warnings.append(f"Redis not available: {exc}")

    return len(errors) == 0, errors, warnings


def check_disk_space(
    local_core_root: Path,
    required_mb: int = 100,
) -> Tuple[bool, List[str]]:
    """Check disk space."""
    errors = []
    try:
        stat = shutil.disk_usage(str(local_core_root))
        free_mb = stat.free / (1024 * 1024)
        if free_mb < required_mb:
            errors.append(
                f"Insufficient disk space: {free_mb:.1f}MB available, "
                f"{required_mb}MB required"
            )
    except Exception as exc:
        logger.debug(f"Could not check disk space: {exc}")

    return len(errors) == 0, errors
