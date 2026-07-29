"""Alembic environment isolated to the mindscape_vectors database."""

from __future__ import annotations

from logging.config import fileConfig
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool


backend_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(backend_dir))

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.database.config import get_postgres_url_vector_session


try:
    vector_url = get_postgres_url_vector_session()
except Exception as exc:
    raise RuntimeError(
        "Vector Alembic requires DATABASE_URL_VECTOR_SESSION and never falls "
        "back to another database."
    ) from exc

config.set_main_option("sqlalchemy.url", vector_url)
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
