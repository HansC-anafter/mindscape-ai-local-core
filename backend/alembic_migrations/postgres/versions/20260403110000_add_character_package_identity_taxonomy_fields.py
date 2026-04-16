"""add character package identity taxonomy fields

Revision ID: 20260403110000
Revises: 20260327235959
Create Date: 2026-04-03 11:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260403110000"
down_revision: Union[str, None] = "20260327235959"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _column_exists(inspector, "character_packages", "identity_scope"):
        op.add_column(
            "character_packages",
            sa.Column("identity_scope", sa.Text(), nullable=True),
        )
    if not _column_exists(inspector, "character_packages", "identity_domain"):
        op.add_column(
            "character_packages",
            sa.Column("identity_domain", sa.Text(), nullable=True),
        )

    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET identity_scope = CASE
                WHEN COALESCE(
                    NULLIF(identity_scope, ''),
                    NULLIF(capability_profile_json->>'identity_scope', '')
                ) IS NOT NULL
                    THEN COALESCE(
                        NULLIF(identity_scope, ''),
                        NULLIF(capability_profile_json->>'identity_scope', '')
                    )
                WHEN COALESCE(NULLIF(package_kind, ''), 'identity') IN ('identity', 'composite')
                    THEN 'full_person_identity'
                ELSE NULL
            END
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET identity_domain = CASE
                WHEN COALESCE(
                    NULLIF(identity_domain, ''),
                    NULLIF(capability_profile_json->>'identity_domain', '')
                ) IS NOT NULL
                    THEN CASE
                        WHEN COALESCE(
                            NULLIF(identity_domain, ''),
                            NULLIF(capability_profile_json->>'identity_domain', '')
                        ) = 'domain_extension'
                            THEN 'other_domain_extension'
                        ELSE COALESCE(
                            NULLIF(identity_domain, ''),
                            NULLIF(capability_profile_json->>'identity_domain', '')
                        )
                    END
                WHEN COALESCE(NULLIF(package_kind, ''), 'identity') IN ('identity', 'composite')
                    THEN 'other_domain_extension'
                ELSE NULL
            END
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET capability_profile_json = jsonb_strip_nulls(
                COALESCE(capability_profile_json, '{}'::jsonb)
                || CASE
                    WHEN identity_scope IS NULL OR identity_scope = ''
                        THEN '{}'::jsonb
                    ELSE jsonb_build_object('identity_scope', identity_scope)
                END
                || CASE
                    WHEN identity_domain IS NULL OR identity_domain = ''
                        THEN '{}'::jsonb
                    ELSE jsonb_build_object('identity_domain', identity_domain)
                END
            )
            WHERE COALESCE(NULLIF(package_kind, ''), 'identity') IN ('identity', 'composite')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE character_packages
            SET capability_profile_json = COALESCE(capability_profile_json, '{}'::jsonb)
                - 'identity_scope'
                - 'identity_domain'
            WHERE COALESCE(NULLIF(package_kind, ''), 'identity') NOT IN ('identity', 'composite')
            """
        )
    )


def downgrade() -> None:
    pass
