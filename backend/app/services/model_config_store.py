"""
Model Config Store

Manages model provider and model configuration storage in PostgreSQL.
"""

import json
from typing import Optional, List
from datetime import datetime
import logging

from sqlalchemy import text

from backend.app.models.model_provider import ModelConfig, ModelType
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class ModelConfigStore(PostgresStoreBase):
    """PostgreSQL-based model configuration store"""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        if db_path is not None:
            logger.warning("ModelConfigStore ignores db_path in Postgres-only mode.")
        if self.factory.get_db_type(self.db_role) != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for ModelConfigStore. Configure PostgreSQL."
            )
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure model_providers/model_configs tables exist (managed by Alembic)."""
        with self.get_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name IN ('model_providers', 'model_configs')"
                )
            )
            existing = {row[0] for row in result.fetchall()}

        missing = {"model_providers", "model_configs"} - existing
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise RuntimeError(
                f"Missing PostgreSQL tables: {missing_list}. "
                "Run: alembic -c backend/alembic.ini upgrade head"
            )

    def get_all_models(
        self,
        model_type: Optional[ModelType] = None,
        enabled: Optional[bool] = None,
        provider: Optional[str] = None,
    ) -> List[ModelConfig]:
        query = "SELECT * FROM model_configs WHERE 1=1"
        params = {}

        if model_type:
            query += " AND model_type = :model_type"
            params["model_type"] = model_type.value

        if enabled is not None:
            query += " AND enabled = :enabled"
            params["enabled"] = enabled

        if provider:
            query += " AND provider_name = :provider"
            params["provider"] = provider

        query += " ORDER BY provider_name, model_type, is_latest DESC, model_name"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()

        return [self._row_to_model(row) for row in rows]

    def get_model_by_id(self, model_id: int) -> Optional[ModelConfig]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM model_configs WHERE id = :id"),
                    {"id": model_id},
                )
                .mappings()
                .fetchone()
            )
        return self._row_to_model(row) if row else None

    def get_model_by_name_and_provider(
        self, model_name: str, provider_name: str, model_type: ModelType
    ) -> Optional[ModelConfig]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                    SELECT * FROM model_configs
                    WHERE model_name = :model_name
                      AND provider_name = :provider_name
                      AND model_type = :model_type
                    """
                    ),
                    {
                        "model_name": model_name,
                        "provider_name": provider_name,
                        "model_type": model_type.value,
                    },
                )
                .mappings()
                .fetchone()
            )
        return self._row_to_model(row) if row else None

    def create_or_update_model(self, model: ModelConfig) -> ModelConfig:
        metadata_json = json.dumps(model.metadata) if model.metadata else "{}"

        with self.transaction() as conn:
            if model.id:
                conn.execute(
                    text(
                        """
                        UPDATE model_configs SET
                            model_name = :model_name,
                            provider_name = :provider_name,
                            model_type = :model_type,
                            display_name = :display_name,
                            description = :description,
                            enabled = :enabled,
                            is_latest = :is_latest,
                            is_recommended = :is_recommended,
                            is_deprecated = :is_deprecated,
                            deprecation_date = :deprecation_date,
                            dimensions = :dimensions,
                            context_window = :context_window,
                            icon = :icon,
                            metadata = :metadata,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": model.id,
                        "model_name": model.model_name,
                        "provider_name": model.provider_name,
                        "model_type": model.model_type.value,
                        "display_name": model.display_name,
                        "description": model.description,
                        "enabled": model.enabled,
                        "is_latest": model.is_latest,
                        "is_recommended": model.is_recommended,
                        "is_deprecated": model.is_deprecated,
                        "deprecation_date": model.deprecation_date,
                        "dimensions": model.dimensions,
                        "context_window": model.context_window,
                        "icon": model.icon,
                        "metadata": metadata_json,
                        "updated_at": datetime.utcnow(),
                    },
                )
                model_id = model.id
            else:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO model_configs (
                            model_name, provider_name, model_type, display_name, description,
                            enabled, is_latest, is_recommended, is_deprecated, deprecation_date,
                            dimensions, context_window, icon, metadata
                        ) VALUES (
                            :model_name, :provider_name, :model_type, :display_name, :description,
                            :enabled, :is_latest, :is_recommended, :is_deprecated, :deprecation_date,
                            :dimensions, :context_window, :icon, :metadata
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "model_name": model.model_name,
                        "provider_name": model.provider_name,
                        "model_type": model.model_type.value,
                        "display_name": model.display_name,
                        "description": model.description,
                        "enabled": model.enabled,
                        "is_latest": model.is_latest,
                        "is_recommended": model.is_recommended,
                        "is_deprecated": model.is_deprecated,
                        "deprecation_date": model.deprecation_date,
                        "dimensions": model.dimensions,
                        "context_window": model.context_window,
                        "icon": model.icon,
                        "metadata": metadata_json,
                    },
                ).fetchone()
                model_id = row[0] if row else model.id

        if model_id:
            model.id = model_id
        return self.get_model_by_id(model_id) or model

    def toggle_model_enabled(
        self, model_id: int, enabled: bool
    ) -> Optional[ModelConfig]:
        with self.transaction() as conn:
            conn.execute(
                text(
                    "UPDATE model_configs SET enabled = :enabled, updated_at = :updated_at WHERE id = :id"
                ),
                {
                    "enabled": enabled,
                    "updated_at": datetime.utcnow(),
                    "id": model_id,
                },
            )
        return self.get_model_by_id(model_id)

    def _row_to_model(self, row) -> ModelConfig:
        metadata = self.deserialize_json(row["metadata"], default={})
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = None

        return ModelConfig(
            id=row["id"],
            model_name=row["model_name"],
            provider_name=row["provider_name"],
            model_type=ModelType(row["model_type"]),
            display_name=row["display_name"],
            description=row["description"] or "",
            enabled=bool(row["enabled"]),
            is_latest=bool(row["is_latest"]),
            is_recommended=bool(row["is_recommended"]),
            is_deprecated=bool(row["is_deprecated"]),
            deprecation_date=row["deprecation_date"],
            dimensions=row["dimensions"],
            context_window=row["context_window"],
            icon=row["icon"],
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
        )

    def initialize_default_models(self):
        from backend.app.routes.core.system_settings.constants import (
            DEFAULT_CHAT_MODELS,
            DEFAULT_EMBEDDING_MODELS,
        )

        existing_models = self.get_all_models()
        if existing_models:
            logger.info("Models already initialized, skipping")
            return

        for model_data in DEFAULT_CHAT_MODELS:
            is_latest = model_data.get("is_latest", False)
            model = ModelConfig(
                model_name=model_data["model_name"],
                provider_name=model_data["provider"],
                model_type=ModelType.CHAT,
                display_name=model_data["model_name"],
                description=model_data.get("description", ""),
                enabled=is_latest,
                is_latest=is_latest,
                is_recommended=model_data.get("is_recommended", False),
                is_deprecated=model_data.get("is_deprecated", False),
                deprecation_date=model_data.get("deprecation_date"),
                context_window=model_data.get("context_window"),
                icon=None,
            )
            self.create_or_update_model(model)

        for model_data in DEFAULT_EMBEDDING_MODELS:
            is_latest = model_data.get("is_latest", False)
            model = ModelConfig(
                model_name=model_data["model_name"],
                provider_name=model_data["provider"],
                model_type=ModelType.EMBEDDING,
                display_name=model_data["model_name"],
                description=model_data.get("description", ""),
                enabled=is_latest,
                is_latest=is_latest,
                is_recommended=model_data.get("is_recommended", False),
                dimensions=model_data.get("dimensions"),
                icon=None,
            )
            self.create_or_update_model(model)

        logger.info("Default models initialized")
