"""Embedding migration analysis helpers."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

async def _analyze_embedding_migration_needs(
    previous_model: Dict[str, str], new_model: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """
    Analyze embedding migration needs by querying historical embedding usage

    Returns detailed information about:
    - Historical models used
    - Last update time for each model
    - Missing time periods in new model
    - Total embeddings count per model
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.database.config import get_vector_postgres_config

        pg_config = get_vector_postgres_config()
        pg_config["connect_timeout"] = 5
        conn = psycopg2.connect(**pg_config)
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SET statement_timeout = 10000")

            cursor.execute(
                """
                SELECT
                    metadata->>'embedding_model' as model_name,
                    metadata->>'embedding_provider' as provider,
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' IS NOT NULL
                GROUP BY metadata->>'embedding_model', metadata->>'embedding_provider'
                ORDER BY last_used DESC
            """
            )

            historical_models = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """,
                (previous_model["model_name"], previous_model["provider"]),
            )

            previous_model_stats = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """,
                (new_model["model_name"], new_model["provider"]),
            )

            new_model_stats = cursor.fetchone()

            from backend.app.services.embedding_migration_store import (
                EmbeddingMigrationStore,
            )
            from backend.app.models.embedding_migration import MigrationStatus

            migration_store = EmbeddingMigrationStore()
            running_migrations = migration_store.list_migrations(
                status=MigrationStatus.IN_PROGRESS
            )
            pending_migrations = migration_store.list_migrations(
                status=MigrationStatus.PENDING
            )
            active_migrations = running_migrations + pending_migrations

            has_active_migration = any(
                m.source_model == previous_model["model_name"]
                and m.target_model == new_model["model_name"]
                for m in active_migrations
            )

            previous_count = (
                previous_model_stats["count"] if previous_model_stats else 0
            )
            new_count = new_model_stats["count"] if new_model_stats else 0
            needs_migration = (
                previous_count > 0
                and (new_count < previous_count or new_count == 0)
                and not has_active_migration
            )

            migration_info = {
                "needs_migration": needs_migration,
                "has_active_migration": has_active_migration,
                "previous_model": {
                    "model_name": previous_model["model_name"],
                    "provider": previous_model["provider"],
                    "total_embeddings": previous_count,
                    "first_used": (
                        previous_model_stats["first_used"].isoformat()
                        if previous_model_stats and previous_model_stats["first_used"]
                        else None
                    ),
                    "last_used": (
                        previous_model_stats["last_used"].isoformat()
                        if previous_model_stats and previous_model_stats["last_used"]
                        else None
                    ),
                    "last_updated": (
                        previous_model_stats["last_updated"].isoformat()
                        if previous_model_stats and previous_model_stats["last_updated"]
                        else None
                    ),
                },
                "new_model": {
                    "model_name": new_model["model_name"],
                    "provider": new_model["provider"],
                    "existing_embeddings": new_count,
                    "first_used": (
                        new_model_stats["first_used"].isoformat()
                        if new_model_stats and new_model_stats["first_used"]
                        else None
                    ),
                    "last_used": (
                        new_model_stats["last_used"].isoformat()
                        if new_model_stats and new_model_stats["last_used"]
                        else None
                    ),
                },
                "historical_models": [
                    {
                        "model_name": row["model_name"],
                        "provider": row["provider"],
                        "count": row["count"],
                        "first_used": (
                            row["first_used"].isoformat() if row["first_used"] else None
                        ),
                        "last_used": (
                            row["last_used"].isoformat() if row["last_used"] else None
                        ),
                        "last_updated": (
                            row["last_updated"].isoformat()
                            if row["last_updated"]
                            else None
                        ),
                    }
                    for row in historical_models
                ],
                "missing_periods": [],
                "migration_recommendation": None,
            }

            if previous_model_stats and previous_model_stats["count"] > 0:
                if (
                    previous_model_stats["first_used"]
                    and previous_model_stats["last_used"]
                ):
                    migration_info["missing_periods"].append(
                        {
                            "from": previous_model_stats["first_used"].isoformat(),
                            "to": previous_model_stats["last_used"].isoformat(),
                            "model": previous_model["model_name"],
                            "count": previous_model_stats["count"],
                        }
                    )

            if needs_migration:
                if new_count == 0:
                    migration_info["migration_recommendation"] = (
                        "New model has no embeddings. Strongly recommend re-embedding all documents to ensure search accuracy."
                    )
                elif new_count < previous_count:
                    missing_count = previous_count - new_count
                    migration_info["migration_recommendation"] = (
                        f"New model is missing {missing_count:,} embeddings. Recommend re-embedding to fill the gap."
                    )
                else:
                    migration_info["migration_recommendation"] = (
                        "Recommend re-embedding to ensure all vectors are generated with the new model."
                    )
            elif has_active_migration:
                migration_info["migration_recommendation"] = (
                    "Active migration task in progress. Please wait for completion before checking again."
                )
            elif new_count >= previous_count and new_count > 0:
                migration_info["migration_recommendation"] = (
                    "New model has sufficient embeddings. Migration may not be necessary."
                )

            return migration_info

        finally:
            conn.close()

    except Exception as e:
        logger.warning(
            f"Failed to analyze embedding migration needs: {e}", exc_info=True
        )
        return {
            "needs_migration": False,
            "has_active_migration": False,
            "previous_model": {
                "model_name": previous_model["model_name"],
                "provider": previous_model["provider"],
                "total_embeddings": None,
            },
            "new_model": {
                "model_name": new_model["model_name"],
                "provider": new_model["provider"],
                "existing_embeddings": 0,
            },
            "historical_models": [],
            "missing_periods": [],
            "migration_recommendation": f"Unable to query embedding status: {str(e)}. Please check database connection.",
            "error": f"Could not query historical data: {str(e)}",
        }
