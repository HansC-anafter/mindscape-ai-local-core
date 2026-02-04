"""add_graph_tables

Revision ID: 20251227000000
Revises: add_workspace_execution_mode
Create Date: 2025-12-27

Adds graph tables for Mind-Lens Graph feature:
- graph_nodes: Graph nodes table
- graph_edges: Graph edges table
- graph_node_entity_links: Bridge table for node-entity links
- graph_node_playbook_links: Bridge table for node-playbook links
- graph_node_intent_links: Bridge table for node-intent links
- mind_lens_profiles: Lens profile configuration table
- mind_lens_active_nodes: Bridge table for lens-active nodes
- mind_lens_workspace_bindings: Bridge table for lens-workspace bindings

See: docs-internal/implementation/mind-lens-graph-implementation-roadmap.md
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20251227000000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create graph tables for SQLite"""

    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("profile_id", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(50), nullable=True),
        sa.Column("size", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.Column("updated_at", sa.String(30), nullable=False),
        sa.CheckConstraint(
            "category IN ('direction', 'action')", name="ck_graph_nodes_category"
        ),
        sa.CheckConstraint(
            "node_type IN ('value', 'worldview', 'aesthetic', 'knowledge', 'strategy', 'role', 'rhythm')",
            name="ck_graph_nodes_node_type",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_graph_nodes_confidence"
        ),
    )

    op.create_index("idx_graph_nodes_profile", "graph_nodes", ["profile_id"])
    op.create_index("idx_graph_nodes_type", "graph_nodes", ["node_type"])
    op.create_index("idx_graph_nodes_category", "graph_nodes", ["category"])

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("profile_id", sa.String(255), nullable=False),
        sa.Column("source_node_id", sa.String(36), nullable=False),
        sa.Column("target_node_id", sa.String(36), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "relation_type IN ('supports', 'conflicts', 'depends_on', 'related_to', 'derived_from', 'applied_to')",
            name="ck_graph_edges_relation_type",
        ),
        sa.CheckConstraint("weight >= 0", name="ck_graph_edges_weight"),
        sa.UniqueConstraint(
            "profile_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            name="uq_graph_edges_no_duplicate",
        ),
    )

    op.create_index("idx_graph_edges_profile", "graph_edges", ["profile_id"])
    op.create_index("idx_graph_edges_source", "graph_edges", ["source_node_id"])
    op.create_index("idx_graph_edges_target", "graph_edges", ["target_node_id"])
    op.create_index("idx_graph_edges_relation", "graph_edges", ["relation_type"])

    op.create_table(
        "graph_node_entity_links",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("graph_node_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("link_type", sa.String(50), server_default="related", nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("graph_node_id", "entity_id", name="uq_graph_node_entity"),
    )

    op.create_table(
        "graph_node_playbook_links",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("graph_node_id", sa.String(36), nullable=False),
        sa.Column("playbook_code", sa.String(255), nullable=False),
        sa.Column("link_type", sa.String(50), server_default="applies", nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "graph_node_id", "playbook_code", name="uq_graph_node_playbook"
        ),
    )

    op.create_table(
        "graph_node_intent_links",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("graph_node_id", sa.String(36), nullable=False),
        sa.Column("intent_id", sa.String(36), nullable=False),
        sa.Column("link_type", sa.String(50), server_default="related", nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["intent_id"], ["intents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("graph_node_id", "intent_id", name="uq_graph_node_intent"),
    )

    op.create_table(
        "mind_lens_profiles",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("profile_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.Column("updated_at", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_lens_profile", "mind_lens_profiles", ["profile_id"])

    op.create_table(
        "mind_lens_active_nodes",
        sa.Column("lens_id", sa.String(36), nullable=False),
        sa.Column("graph_node_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("lens_id", "graph_node_id"),
        sa.ForeignKeyConstraint(
            ["lens_id"], ["mind_lens_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "mind_lens_workspace_bindings",
        sa.Column("lens_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("lens_id", "workspace_id"),
        sa.ForeignKeyConstraint(
            ["lens_id"], ["mind_lens_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_single_lens"),
    )


def downgrade() -> None:
    """Drop all graph tables"""
    op.drop_table("mind_lens_workspace_bindings")
    op.drop_table("mind_lens_active_nodes")
    op.drop_index("idx_lens_profile", table_name="mind_lens_profiles")
    op.drop_table("mind_lens_profiles")
    op.drop_table("graph_node_intent_links")
    op.drop_table("graph_node_playbook_links")
    op.drop_table("graph_node_entity_links")
    op.drop_index("idx_graph_edges_relation", table_name="graph_edges")
    op.drop_index("idx_graph_edges_target", table_name="graph_edges")
    op.drop_index("idx_graph_edges_source", table_name="graph_edges")
    op.drop_index("idx_graph_edges_profile", table_name="graph_edges")
    op.drop_table("graph_edges")
    op.drop_index("idx_graph_nodes_category", table_name="graph_nodes")
    op.drop_index("idx_graph_nodes_type", table_name="graph_nodes")
    op.drop_index("idx_graph_nodes_profile", table_name="graph_nodes")
    op.drop_table("graph_nodes")
