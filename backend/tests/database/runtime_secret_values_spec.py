from __future__ import annotations

import os

import pytest

from backend.app.database import config as db_config
from backend.app.database.secret_values import read_secret_file


def _clear_db_url_caches() -> None:
    db_config._resolved_url_cache.clear()
    db_config._resolved_session_url_cache.clear()
    db_config._resolved_readonly_url_cache.clear()


def _clear_vector_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("POSTGRES_VECTOR_") or name.startswith("DATABASE_URL_VECTOR"):
            monkeypatch.delenv(name, raising=False)


def test_secret_file_accepts_one_utf8_line_with_optional_newline(tmp_path):
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_bytes("密碼-p@ss:/?#\n".encode("utf-8"))

    assert read_secret_file(str(secret_file)) == "密碼-p@ss:/?#"


@pytest.mark.parametrize("content", [b"", b"first\nsecond", b"nul\x00value"])
def test_secret_file_rejects_invalid_content(tmp_path, content):
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_bytes(content)

    with pytest.raises(ValueError, match="one non-empty line"):
        read_secret_file(str(secret_file))


def test_secret_file_rejects_symlink_and_oversized_content(tmp_path):
    target = tmp_path / "target"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        read_secret_file(str(link))

    target.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError, match="size limit"):
        read_secret_file(str(target))


def test_vector_urls_are_built_from_secret_file_and_quote_credentials(
    monkeypatch, tmp_path
):
    _clear_vector_environment(monkeypatch)
    _clear_db_url_caches()
    secret_file = tmp_path / "runtime-secret"
    secret_file.write_text("p@ss:/?# value", encoding="utf-8")
    monkeypatch.setenv("POSTGRES_VECTOR_PASSWORD_FILE", str(secret_file))
    monkeypatch.setenv("POSTGRES_VECTOR_USER", "runtime@role")
    monkeypatch.setenv("POSTGRES_VECTOR_HOST", "pgbouncer")
    monkeypatch.setenv("POSTGRES_VECTOR_PORT", "6432")
    monkeypatch.setenv("POSTGRES_VECTOR_DB", "mindscape_vectors")
    monkeypatch.setenv("POSTGRES_VECTOR_SESSION_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_VECTOR_SESSION_PORT", "5432")
    monkeypatch.setenv("POSTGRES_VECTOR_SESSION_DB", "mindscape_vectors")
    monkeypatch.setenv("POSTGRES_VECTOR_READONLY_HOST", "pgbouncer")
    monkeypatch.setenv("POSTGRES_VECTOR_READONLY_PORT", "6432")
    monkeypatch.setenv("POSTGRES_VECTOR_READONLY_DB", "mindscape_vectors_readonly")

    transaction = db_config.get_postgres_url_vector()
    session = db_config.get_postgres_url_vector_session()
    readonly = db_config.get_postgres_url_vector_readonly()

    quoted_credential = "runtime%40role:p%40ss%3A%2F%3F%23%20value"
    assert transaction == f"postgresql://{quoted_credential}@pgbouncer:6432/mindscape_vectors"
    assert session == f"postgresql://{quoted_credential}@postgres:5432/mindscape_vectors"
    assert readonly == (
        f"postgresql://{quoted_credential}@pgbouncer:6432/mindscape_vectors_readonly"
    )


def test_vector_url_fails_closed_when_no_password_source_exists(monkeypatch):
    _clear_vector_environment(monkeypatch)
    _clear_db_url_caches()
    monkeypatch.setenv("POSTGRES_PASSWORD", "core-password-must-not-cross-role")
    monkeypatch.delenv("POSTGRES_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("POSTGRES_VECTOR_HOST", "pgbouncer")

    with pytest.raises(ValueError, match="PostgreSQL vector configuration missing"):
        db_config.get_postgres_url_vector()
