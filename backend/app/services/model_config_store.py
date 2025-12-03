"""
Model Config Store

Manages model provider and model configuration storage in SQLite database.
"""

import json
import sqlite3
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import logging

from backend.app.models.model_provider import ModelConfig, ModelProviderConfig, ModelType

logger = logging.getLogger(__name__)


class ModelConfigStore:
    """SQLite-based model configuration store"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize model config store

        Args:
            db_path: Path to SQLite database (default: ./data/mindscape.db)
        """
        if db_path is None:
            db_path = Path("./data/mindscape.db")
        else:
            db_path = Path(db_path)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize model_providers and model_configs tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create model_providers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT NOT NULL UNIQUE,
                api_key_setting_key TEXT NOT NULL,
                base_url TEXT,
                enabled BOOLEAN DEFAULT 1,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create model_configs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                model_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                enabled BOOLEAN DEFAULT 0,
                is_latest BOOLEAN DEFAULT 0,
                is_recommended BOOLEAN DEFAULT 0,
                is_deprecated BOOLEAN DEFAULT 0,
                deprecation_date TEXT,
                dimensions INTEGER,
                context_window INTEGER,
                icon TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model_name, provider_name, model_type)
            )
        """)

        conn.commit()
        conn.close()

    def get_all_models(
        self,
        model_type: Optional[ModelType] = None,
        enabled: Optional[bool] = None,
        provider: Optional[str] = None
    ) -> List[ModelConfig]:
        """
        Get all models with optional filters

        Args:
            model_type: Filter by model type (chat or embedding)
            enabled: Filter by enabled status
            provider: Filter by provider name

        Returns:
            List of ModelConfig objects
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM model_configs WHERE 1=1"
        params = []

        if model_type:
            query += " AND model_type = ?"
            params.append(model_type.value)

        if enabled is not None:
            query += " AND enabled = ?"
            params.append(1 if enabled else 0)

        if provider:
            query += " AND provider_name = ?"
            params.append(provider)

        query += " ORDER BY provider_name, model_type, is_latest DESC, model_name"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        models = []
        for row in rows:
            model = self._row_to_model(row)
            models.append(model)

        return models

    def get_model_by_id(self, model_id: int) -> Optional[ModelConfig]:
        """Get model by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM model_configs WHERE id = ?", (model_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_model(row)
        return None

    def get_model_by_name_and_provider(
        self,
        model_name: str,
        provider_name: str,
        model_type: ModelType
    ) -> Optional[ModelConfig]:
        """Get model by name, provider, and type"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM model_configs WHERE model_name = ? AND provider_name = ? AND model_type = ?",
            (model_name, provider_name, model_type.value)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_model(row)
        return None

    def create_or_update_model(self, model: ModelConfig) -> ModelConfig:
        """Create or update a model configuration"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        metadata_json = json.dumps(model.metadata) if model.metadata else "{}"

        if model.id:
            cursor.execute("""
                UPDATE model_configs SET
                    model_name = ?,
                    provider_name = ?,
                    model_type = ?,
                    display_name = ?,
                    description = ?,
                    enabled = ?,
                    is_latest = ?,
                    is_recommended = ?,
                    is_deprecated = ?,
                    deprecation_date = ?,
                    dimensions = ?,
                    context_window = ?,
                    icon = ?,
                    metadata = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                model.model_name,
                model.provider_name,
                model.model_type.value,
                model.display_name,
                model.description,
                1 if model.enabled else 0,
                1 if model.is_latest else 0,
                1 if model.is_recommended else 0,
                1 if model.is_deprecated else 0,
                model.deprecation_date,
                model.dimensions,
                model.context_window,
                model.icon,
                metadata_json,
                model.id
            ))
        else:
            cursor.execute("""
                INSERT INTO model_configs (
                    model_name, provider_name, model_type, display_name, description,
                    enabled, is_latest, is_recommended, is_deprecated, deprecation_date,
                    dimensions, context_window, icon, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model.model_name,
                model.provider_name,
                model.model_type.value,
                model.display_name,
                model.description,
                1 if model.enabled else 0,
                1 if model.is_latest else 0,
                1 if model.is_recommended else 0,
                1 if model.is_deprecated else 0,
                model.deprecation_date,
                model.dimensions,
                model.context_window,
                model.icon,
                metadata_json
            ))
            model.id = cursor.lastrowid

        conn.commit()
        conn.close()

        return self.get_model_by_id(model.id) or model

    def toggle_model_enabled(self, model_id: int, enabled: bool) -> Optional[ModelConfig]:
        """Enable or disable a model"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE model_configs SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if enabled else 0, model_id)
        )

        conn.commit()
        conn.close()

        return self.get_model_by_id(model_id)

    def _row_to_model(self, row: sqlite3.Row) -> ModelConfig:
        """Convert database row to ModelConfig"""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse metadata for model {row['id']}")

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
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def initialize_default_models(self):
        """Initialize default models from hardcoded list"""
        from backend.app.routes.core.system_settings import (
            DEFAULT_CHAT_MODELS,
            DEFAULT_EMBEDDING_MODELS
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

