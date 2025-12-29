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

# ===== SQLite Models =====
# 注意：現狀中 SQLite 無統一 Base，各 store 使用 sqlite3
# 此處需要建立 SQLite 專用的 metadata，或調整為使用 StoreBase 方式
#
# 選項 1：建立新的 SQLite Base（需新增）
# from app.database.sqlite_base import SQLiteBase
# target_metadata = SQLiteBase.metadata
#
# 選項 2：保持 sqlite3 方式，但用 Alembic 僅記錄 DDL（不依賴 SQLAlchemy models）
# 此方式不需要建立 SQLAlchemy metadata，但需手動編寫 DDL 遷移檔

# 暫時使用空 metadata（實際實施時需補齊）
# TODO: 建立 SQLite metadata 或決定使用選項 2
target_metadata = None

# Set SQLite URL（統一使用 mindscape.db）
data_dir = Path(backend_dir.parent / "data")
data_dir.mkdir(parents=True, exist_ok=True)
db_path = data_dir / "mindscape.db"  # 統一使用 mindscape.db
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.absolute()}")


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

