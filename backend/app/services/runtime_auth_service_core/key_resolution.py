"""Encryption key resolution for RuntimeAuthService."""

import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def resolve_encryption_key(key_file: str) -> str:
    """Resolve the runtime encryption key through the established layers."""
    key = os.getenv("RUNTIME_ENCRYPTION_KEY")
    if key:
        return key

    key_path = key_file
    try:
        if os.path.isfile(key_path):
            with open(key_path, "r") as f:
                key = f.read().strip()
            if key:
                logger.info("Encryption key loaded from persistent file")
                return key
    except OSError as e:
        logger.warning(f"Failed to read encryption key file: {e}")

    is_production = os.getenv("ENVIRONMENT", "development").lower() in (
        "production",
        "staging",
    )
    if is_production:
        raise RuntimeError(
            "RUNTIME_ENCRYPTION_KEY is not set and no persistent key file found. "
            "Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
            "and add it to your .env file."
        )

    new_key = Fernet.generate_key().decode()
    try:
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "w") as f:
            f.write(new_key)
        os.chmod(key_path, 0o600)
        logger.warning(
            f"Auto-generated encryption key persisted to {key_path}. "
            f"Set RUNTIME_ENCRYPTION_KEY env var for production."
        )
    except OSError as e:
        logger.warning(
            f"Could not persist encryption key to {key_path}: {e}. "
            f"Key will be lost on restart."
        )
    return new_key
