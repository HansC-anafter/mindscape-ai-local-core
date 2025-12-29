from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import os
import sys
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ===== PostgreSQL ORM Models =====
# Import PostgreSQL Base and models
# 注意：需確認執行環境的 PYTHONPATH 能找到 app.database，避免後續匯入問題
from app.database import Base
from app.models.sonic_space.sonic_space import (
    SonicAudioAsset,
    SonicLicenseCard,
    SonicSegment,
    SonicEmbedding,
    SonicIntentCard,
    SonicCandidateSet,
    SonicDecisionTrace,
    SonicBookmark,
    SonicSoundKit,
    SonicSoundKitItem,
    SonicPerceptualAxes,
    SonicExportAudit,
)
# 其他 PostgreSQL models（如 mindscape_personal 等，待 init_db.py 轉為遷移後加入）

target_metadata = Base.metadata

# ===== Use PostgreSQL URL =====
# 注意：移除 SQLite fallback，PostgreSQL 為必需
from app.database.config import get_postgres_url
try:
    postgres_url = get_postgres_url()
    config.set_main_option("sqlalchemy.url", postgres_url)
except Exception as e:
    raise RuntimeError(f"Failed to get PostgreSQL URL: {e}. PostgreSQL is required for vector storage and Sonic Space.")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

