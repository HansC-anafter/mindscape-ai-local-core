"""Validates environment and dependencies before migration."""

import logging
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validates environment requirements and dependencies."""

    def __init__(self):
        pass

    def validate_postgres_connection(self, postgres_url: str) -> bool:
        """Validate PostgreSQL connection."""
        try:
            engine = create_engine(postgres_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            return False

    def validate_postgres_extensions(self, postgres_url: str, required_extensions: List[str]) -> Dict[str, bool]:
        """Check if required PostgreSQL extensions are installed."""
        results = {}
        try:
            engine = create_engine(postgres_url)
            with engine.connect() as conn:
                for ext in required_extensions:
                    result = conn.execute(
                        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = :ext)"),
                        {"ext": ext}
                    )
                    results[ext] = result.scalar()
        except Exception as e:
            logger.error(f"Failed to check extensions: {e}")
            return {ext: False for ext in required_extensions}

        return results

    def validate_sqlite_permissions(self, db_path: str) -> bool:
        """Validate SQLite database file permissions."""
        from pathlib import Path
        db_file = Path(db_path)

        if not db_file.parent.exists():
            try:
                db_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Cannot create SQLite directory: {e}")
                return False

        # Check write permissions
        try:
            db_file.touch(exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Cannot write to SQLite database: {e}")
            return False

    def validate_environment(self, db_type: str, requirements: Dict) -> Dict[str, bool]:
        """Validate environment requirements."""
        results = {}

        if db_type == "postgres":
            postgres_url = requirements.get("postgres_url")
            if not postgres_url:
                results["connection"] = False
                return results

            results["connection"] = self.validate_postgres_connection(postgres_url)

            env_reqs = requirements.get("environment_requirements", {}).get("postgres", {})
            required_extensions = env_reqs.get("extensions", [])
            if required_extensions:
                ext_results = self.validate_postgres_extensions(postgres_url, required_extensions)
                results.update(ext_results)

        elif db_type == "sqlite":
            db_path = requirements.get("sqlite_path")
            if db_path:
                results["permissions"] = self.validate_sqlite_permissions(db_path)
            else:
                results["permissions"] = False

        return results

