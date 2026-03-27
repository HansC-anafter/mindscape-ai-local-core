"""add character package contract fields

Revision ID: 20260327235959
Revises: 20260326160000
Create Date: 2026-03-27 23:59:59
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260327235959"
down_revision: Union[str, None] = "20260326160000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _column_exists(inspector, "character_packages", "package_kind"):
        op.add_column(
            "character_packages",
            sa.Column("package_kind", sa.Text(), nullable=False, server_default="identity"),
        )
    if not _column_exists(inspector, "character_packages", "capability_profile_json"):
        op.add_column(
            "character_packages",
            sa.Column(
                "capability_profile_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET package_kind = COALESCE(NULLIF(package_kind, ''), 'identity')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET capability_profile_json = jsonb_build_object(
                'supported_consumption_modes',
                CASE
                    WHEN recommended_use_modes_json IS NULL OR recommended_use_modes_json = '[]'::jsonb
                        THEN '["reference_only","adapter_only","hybrid"]'::jsonb
                    ELSE recommended_use_modes_json
                END,
                'required_review_modes',
                '["identity_visual_acceptance"]'::jsonb,
                'required_runtime_features',
                '[]'::jsonb,
                'supports_model_families',
                COALESCE(supported_families_json, '[]'::jsonb),
                'degradation_strategy',
                to_jsonb('reference_or_adapter_fallback'::text)
            )
            WHERE capability_profile_json IS NULL OR capability_profile_json = '{}'::jsonb
            """
        )
    )

    op.alter_column("character_packages", "package_kind", server_default=None)
    op.alter_column("character_packages", "capability_profile_json", server_default=None)


def downgrade() -> None:
    pass
