from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import os
import sys
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
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
from app.database import Base
from app.database.models import mind_lens, artifact

# Dynamically discover and import capability models
# Core principle: no hardcoded capability module names, fully dynamic discovery
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _discover_and_import_capability_models():
    """
    Dynamically discover and import all capability module models.

    Scans all subdirectories under app/models and attempts to import model files.
    Silently skips if import fails (module may not exist or be installed).
    """
    models_dir = backend_dir / "app" / "models"
    if not models_dir.exists():
        return

    for model_subdir in models_dir.iterdir():
        if not model_subdir.is_dir():
            continue

        if model_subdir.name.startswith("_"):
            continue

        try:
            module_name = f"app.models.{model_subdir.name}"
            try:
                importlib.import_module(module_name)
            except ImportError:
                pass

            for py_file in model_subdir.glob("*.py"):
                if py_file.name == "__init__.py":
                    continue

                module_path = f"{module_name}.{py_file.stem}"
                try:
                    importlib.import_module(module_path)
                    logger.debug(
                        f"Successfully imported capability model: {module_path}"
                    )
                except ImportError as e:
                    logger.debug(
                        f"Skipped optional capability model {module_path}: {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error importing capability model {module_path}: {e}"
                    )
        except Exception as e:
            logger.debug(f"Skipped capability model directory {model_subdir.name}: {e}")


_discover_and_import_capability_models()

target_metadata = Base.metadata

# ===== Use PostgreSQL URL =====
from app.database.config import get_postgres_url

try:
    postgres_url = get_postgres_url()
    config.set_main_option("sqlalchemy.url", postgres_url)
    print(
        f"Alembic using PostgreSQL: {postgres_url.split('@')[-1] if '@' in postgres_url else postgres_url}"
    )

    # Dynamically set version_locations to include postgres/versions
    # We need both the common versions and postgres versions
    common_versions = os.path.join(backend_dir, "alembic_migrations", "versions")
    postgres_versions = os.path.join(
        backend_dir, "alembic_migrations", "postgres", "versions"
    )

    # Use os.pathsep to combine (alembic.ini sets version_path_separator = os)
    config.set_main_option(
        "version_locations", f"{common_versions}{os.pathsep}{postgres_versions}"
    )
    print(f"Version locations: {common_versions}, {postgres_versions}")

except Exception as e:
    print(f"Warning: Failed to get PostgreSQL URL: {e}")
    print("Alembic will use default SQLite configuration")
    data_dir = Path(backend_dir.parent / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "mindscape.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.absolute()}")

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
