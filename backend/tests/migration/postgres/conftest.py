import pytest
import os
import sys
from pathlib import Path
from typing import Generator, Any

# Ensure backend module is in sys.path
BACKEND_DIR = Path(__file__).parent.parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

# Also add project root (parent of backend) to support "backend.app" imports
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def cvp_env_setup() -> Generator[None, None, None]:
    """
    Setup environment variables for Capability Verification Protocol (CVP).
    Ensures that we are running in a test mode and targeting the correct DB.
    """
    # Set verification mode flag
    os.environ["MINDSCAPE_CVP_MODE"] = "true"

    # Ensure we don't accidentally write to production SQLite if logic slips
    # (Though we are testing Postgres, safety first)
    original_db_url = os.environ.get("DATABASE_URL")

    # In a real scenario, we might spin up a test container or use a specific test DB
    # For now, we assume the local docker environment is available for dev testing
    # but we might want to qualify the URL to a test database if possible.
    # os.environ["DATABASE_URL"] = "postgresql://user:password@localhost:5432/mindscape_test"

    yield

    # Teardown: Restore environment
    if os.environ.get("MINDSCAPE_CVP_MODE"):
        del os.environ["MINDSCAPE_CVP_MODE"]

    if original_db_url:
        os.environ["DATABASE_URL"] = original_db_url
    else:
        # If it wasn't set, remove it if we set it (logic above commented out for now)
        pass


@pytest.fixture(scope="module")
def mock_postgres_config(cvp_env_setup: Any) -> Any:
    """
    Provides a mock configuration for PostgreSQL connection testing.
    This simulates what the application would see when configured for Postgres.
    """
    return {
        "DATABASE_URL": os.getenv(
            "DATABASE_URL",
            "postgresql://mindscape:mindscape_password@localhost:5433/mindscape_vectors",
        ),
        "DB_TYPE": "postgres",
    }


@pytest.fixture
def sqlite_prohibited_hook() -> Generator[None, None, None]:
    """
    Fixture to detect and prohibit SQLite usage during Postgres tests.
    This can be used in specific tests that assert 'No SQLite'.
    """
    import sqlite3

    original_connect = sqlite3.connect

    def prohibited_connect(*args, **kwargs):
        raise RuntimeError("SQLite access prohibited during CVP Postgres Verification!")

    sqlite3.connect = prohibited_connect

    yield

    sqlite3.connect = original_connect


@pytest.fixture(scope="function")
def postgres_db(mock_postgres_config):
    """
    Sets up a Postgres database for testing.
    Creates tables and yields a healthy state.
    """
    # Set env vars
    os.environ["DATABASE_URL"] = mock_postgres_config["DATABASE_URL"]
    # ConnectionFactory logic uses DATABASE_URL for type check,
    # but create_engine logic uses POSTGRES_URL (via get_postgres_url)
    os.environ["POSTGRES_URL"] = mock_postgres_config["DATABASE_URL"]
    os.environ["MINDSCAPE_FORCE_POSTGRES"] = "true"

    # Import Base and Factory
    from app.database.connection_factory import ConnectionFactory
    from app.database import Base

    # Ensure models are imported so they are registered with Base.metadata
    from app.database.models import mind_lens, artifact  # noqa

    # Reset factory to pick up new env vars
    ConnectionFactory.reset()
    factory = ConnectionFactory()
    engine = factory._get_postgres_engine()

    # Create tables
    Base.metadata.create_all(bind=engine)

    yield

    # Teardown
    Base.metadata.drop_all(bind=engine)
    ConnectionFactory.reset()
