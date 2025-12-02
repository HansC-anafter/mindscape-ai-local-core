"""
Migration 004: Add workspace storage configuration fields

Adds storage_base_path, artifacts_dir, uploads_dir, storage_config
to workspaces table for path binding and storage management.

⚠️ 資料遷移：為 storage_base_path 為 NULL 的 workspace 設預設路徑或標記 requires_manual_setup，
並處理 artifacts.storage_ref 為空的情況。
"""
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate_004_add_workspace_storage_config(cursor):
    """
    Apply migration 004 with data migration

    ⚠️ 重要：資料遷移策略
    1. 為現有 Workspace（storage_base_path 為 NULL）設定預設路徑或標記 requires_manual_setup
    2. 處理現有 Artifact 的 storage_ref 為空或無效的情況
    """
    logger.info("Applying migration 004: Add workspace storage config")

    # 添加新欄位（SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS）
    for column_name in ['storage_base_path', 'artifacts_dir', 'uploads_dir', 'storage_config']:
        try:
            cursor.execute(f'ALTER TABLE workspaces ADD COLUMN {column_name} TEXT')
        except Exception as e:
            # 如果欄位已存在，忽略錯誤
            if "duplicate column name" not in str(e).lower() and "already exists" not in str(e).lower():
                raise
            logger.warning(f"Column {column_name} may already exist: {e}")

    # ⚠️ 資料遷移：為現有 Workspace 設定預設路徑或標記 requires_manual_setup
    logger.info("Migrating existing workspaces...")

    # 獲取 Local File System 配置
    default_base_path = None
    try:
        from backend.app.services.stores.services.tool_registry import ToolRegistryService
        tool_registry = ToolRegistryService()
        # 從 tool_connections 表讀取配置
        from backend.app.services.stores.services.mindscape_store import MindscapeStore
        store = MindscapeStore()
        connections = store.tool_connections.list_connections_by_type("local_filesystem")

        if connections:
            # 優先從 config 讀取 allowed_directories
            config = connections[0].config or {}
            if isinstance(config, str):
                config = json.loads(config)
            allowed_dirs = config.get("allowed_directories", [])
            if allowed_dirs:
                default_base_path = allowed_dirs[0]
            elif hasattr(connections[0], 'endpoint') and connections[0].endpoint:
                # 後備：從 endpoint 讀取
                default_base_path = connections[0].endpoint
    except Exception as e:
        logger.warning(f"Failed to get default storage path for migration: {e}")
        default_base_path = None

    # 更新現有 Workspace（storage_base_path 為 NULL 的）
    cursor.execute('''
        SELECT id, title FROM workspaces
        WHERE storage_base_path IS NULL OR storage_base_path = ''
    ''')
    workspaces = cursor.fetchall()

    migrated_count = 0
    requires_manual_setup = []

    for workspace_id, title in workspaces:
        if default_base_path:
            # 使用預設路徑 + Mindscape/<workspace_name>
            workspace_path = Path(default_base_path).expanduser() / "Mindscape" / title
            workspace_path = str(workspace_path.resolve())

            cursor.execute('''
                UPDATE workspaces
                SET storage_base_path = ?,
                    artifacts_dir = 'artifacts',
                    uploads_dir = 'uploads',
                    storage_config = ?
                WHERE id = ?
            ''', (
                workspace_path,
                json.dumps({
                    "bucket_strategy": "playbook_code",
                    "naming_rule": "slug-v{version}-{timestamp}.{ext}"
                }),
                workspace_id
            ))

            logger.info(f"Migrated workspace {workspace_id} to {workspace_path}")
            migrated_count += 1
        else:
            # 無預設路徑，標記需要手動設定
            cursor.execute('''
                UPDATE workspaces
                SET artifacts_dir = 'artifacts',
                    uploads_dir = 'uploads',
                    storage_config = ?
                WHERE id = ?
            ''', (
                json.dumps({
                    "requires_manual_setup": True,
                    "bucket_strategy": "playbook_code",
                    "naming_rule": "slug-v{version}-{timestamp}.{ext}"
                }),
                workspace_id
            ))

            requires_manual_setup.append(workspace_id)
            logger.warning(f"Workspace {workspace_id} requires manual storage path setup")

    # ⚠️ 資料遷移：處理現有 Artifact 的 storage_ref 為空或無效的情況
    # 注意：Artifact 的 storage_ref 為空是正常的（某些類型不寫檔，如 checklist、draft），
    # 但如果有 storage_ref 但路徑無效，需要標記以便後續處理
    logger.info("Checking existing artifacts with invalid storage_ref...")

    try:
        cursor.execute('''
            SELECT id, workspace_id, storage_ref, playbook_code
            FROM artifacts
            WHERE storage_ref IS NOT NULL AND storage_ref != ''
        ''')
        artifacts = cursor.fetchall()

        invalid_artifacts = []
        for artifact_id, workspace_id, storage_ref, playbook_code in artifacts:
            try:
                artifact_path = Path(storage_ref)
                if not artifact_path.exists():
                    # 路徑不存在，標記為需要檢查
                    invalid_artifacts.append(artifact_id)
                    logger.warning(
                        f"Artifact {artifact_id} has invalid storage_ref: {storage_ref}"
                    )
            except Exception as e:
                logger.warning(f"Error checking artifact {artifact_id} storage_ref: {e}")
                invalid_artifacts.append(artifact_id)

        if invalid_artifacts:
            logger.warning(
                f"Found {len(invalid_artifacts)} artifacts with invalid storage_ref. "
                "These may need manual review."
            )
    except Exception as e:
        # artifacts 表可能不存在（如果 migration 003 還沒執行）
        logger.debug(f"Artifacts table may not exist yet: {e}")

    logger.info(
        f"Migration 004 completed: "
        f"{migrated_count} workspaces migrated, "
        f"{len(requires_manual_setup)} require manual setup"
    )

    if requires_manual_setup:
        logger.warning(
            f"Workspaces requiring manual storage path setup: {requires_manual_setup}"
        )


def rollback_004_add_workspace_storage_config(cursor):
    """Rollback migration 004"""
    logger.info("Rolling back migration 004: Remove workspace storage config")
    # SQLite 不支持 DROP COLUMN，需要重建表
    # 這裡只記錄，實際回滾需要重建表
    logger.warning("SQLite does not support DROP COLUMN. Rollback requires table recreation.")

