"""add_session_liff_context_updated_at

Revision ID: 20260104082924
Revises: 20251227181638
Create Date: 2026-01-04 08:29:24.000000

添加 liff_context 和 updated_at 字段到 yogacoach_sessions 表（Cloud DB 修复）

修复旧的 cloud DB 迁移脚本中缺少的字段：
- liff_context (JSONB, nullable=True) - 用于存储 LINE LIFF 上下文
- updated_at (DateTime, auto-update) - 用于跟踪记录更新时间

此迁移脚本用于修复由 20251227181638_add_yogacoach_tables.py 创建的表结构。

⚠️ 注意：此迁移脚本仅用于修复旧的 cloud DB 迁移脚本。
⚠️ Tenant-specific 表应该通过 tenant-db-provisioner 在 tenant DB 中创建。

相关文档：
- YOGACOACH_SCHEMA_MISMATCH_ANALYSIS.md
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20260104082924'
down_revision = '20251227181638'
branch_labels = None
depends_on = None


def upgrade():
    """
    添加 liff_context 和 updated_at 字段到 yogacoach_sessions 表（Cloud DB）
    """
    print("\n🔧 添加 liff_context 和 updated_at 字段到 yogacoach_sessions 表（Cloud DB）...")

    # 检查字段是否已存在（避免重複執行）
    # 使用 DO 語句檢查字段是否存在
    op.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'yogacoach_sessions'
                AND column_name = 'liff_context'
            ) THEN
                ALTER TABLE yogacoach_sessions
                ADD COLUMN liff_context JSONB;
            END IF;
        END $$;
    """))

    # 添加 updated_at 字段（DateTime，自動更新）
    op.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'yogacoach_sessions'
                AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE yogacoach_sessions
                ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            END IF;
        END $$;
    """))

    # 更新現有記錄的 updated_at 為 created_at（如果 created_at 存在）
    op.execute(text("""
        UPDATE yogacoach_sessions
        SET updated_at = created_at
        WHERE updated_at IS NULL AND created_at IS NOT NULL
    """))

    print("  ✅ liff_context 和 updated_at 字段添加完成（Cloud DB）")


def downgrade():
    """
    回滾：移除 liff_context 和 updated_at 字段
    """
    print("\n🔧 回滾 liff_context 和 updated_at 字段（Cloud DB）...")

    # 移除字段
    op.drop_column('yogacoach_sessions', 'updated_at')
    op.drop_column('yogacoach_sessions', 'liff_context')

    print("  ✅ liff_context 和 updated_at 字段已移除（Cloud DB）")

