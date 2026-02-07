"""Add Mind-Lens graph + observability tables

Revision ID: 20260130000007
Revises: 20260130000006
Create Date: 2026-01-30 00:00:07.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000007"
down_revision = "20260130000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Graph Nodes ---
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("size", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_graph_nodes_profile", "graph_nodes", ["profile_id"])
    op.create_index("idx_graph_nodes_type", "graph_nodes", ["node_type"])
    op.create_index("idx_graph_nodes_category", "graph_nodes", ["category"])

    # --- Graph Edges ---
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("source_node_id", sa.String(length=36), nullable=False),
        sa.Column("target_node_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('supports', 'conflicts', 'depends_on', 'related_to', 'derived_from', 'applied_to')",
            name="ck_graph_edges_relation_type",
        ),
        sa.CheckConstraint("weight >= 0", name="ck_graph_edges_weight"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            name="uq_graph_edges_no_duplicate",
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_graph_edges_profile", "graph_edges", ["profile_id"])
    op.create_index("idx_graph_edges_source", "graph_edges", ["source_node_id"])
    op.create_index("idx_graph_edges_target", "graph_edges", ["target_node_id"])
    op.create_index("idx_graph_edges_relation", "graph_edges", ["relation_type"])

    # --- Graph Links ---
    op.create_table(
        "graph_node_entity_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_node_id", sa.String(length=36), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=50), server_default="related", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_node_id", "entity_id", name="uq_graph_node_entity"),
        sa.ForeignKeyConstraint(["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "graph_node_playbook_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_node_id", sa.String(length=36), nullable=False),
        sa.Column("playbook_code", sa.String(length=255), nullable=False),
        sa.Column("link_type", sa.String(length=50), server_default="applies", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "graph_node_id", "playbook_code", name="uq_graph_node_playbook"
        ),
        sa.ForeignKeyConstraint(["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "graph_node_intent_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_node_id", sa.String(length=36), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=50), server_default="related", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_node_id", "intent_id", name="uq_graph_node_intent"),
        sa.ForeignKeyConstraint(["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["intent_id"], ["intents.id"], ondelete="CASCADE"),
    )

    # --- Mind-Lens Profiles ---
    op.create_table(
        "mind_lens_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_lens_profile", "mind_lens_profiles", ["profile_id"])

    op.create_table(
        "mind_lens_active_nodes",
        sa.Column("lens_id", sa.String(length=36), nullable=False),
        sa.Column("graph_node_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("lens_id", "graph_node_id"),
        sa.ForeignKeyConstraint(["lens_id"], ["mind_lens_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graph_node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "mind_lens_workspace_bindings",
        sa.Column("lens_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("lens_id", "workspace_id"),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_single_lens"),
        sa.ForeignKeyConstraint(["lens_id"], ["mind_lens_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "lens_profile_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preset_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="keep", nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('off', 'keep', 'emphasize')", name="ck_lens_profile_nodes_state"
        ),
        sa.UniqueConstraint("preset_id", "node_id", name="uq_lens_profile_nodes"),
        sa.ForeignKeyConstraint(["preset_id"], ["mind_lens_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_lens_profile_nodes_preset", "lens_profile_nodes", ["preset_id"])
    op.create_index("idx_lens_profile_nodes_node", "lens_profile_nodes", ["node_id"])

    op.create_table(
        "workspace_lens_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('off', 'keep', 'emphasize')", name="ck_workspace_lens_overrides_state"
        ),
        sa.UniqueConstraint("workspace_id", "node_id", name="uq_workspace_lens_overrides"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["graph_nodes.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_workspace_overrides_ws", "workspace_lens_overrides", ["workspace_id"])
    op.create_index("idx_workspace_overrides_node", "workspace_lens_overrides", ["node_id"])

    # --- Lens Snapshots ---
    op.create_table(
        "lens_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("effective_lens_hash", sa.String(length=16), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("nodes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("effective_lens_hash", name="uq_lens_snapshots_hash"),
    )
    op.create_index("idx_lens_snapshots_hash", "lens_snapshots", ["effective_lens_hash"])
    op.create_index("idx_lens_snapshots_profile", "lens_snapshots", ["profile_id"])
    op.create_index("idx_lens_snapshots_workspace", "lens_snapshots", ["workspace_id"])

    # --- Lens Receipts ---
    op.create_table(
        "lens_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("effective_lens_hash", sa.String(length=16), nullable=False),
        sa.Column("triggered_nodes_json", sa.Text(), nullable=True),
        sa.Column("base_output", sa.Text(), nullable=True),
        sa.Column("lens_output", sa.Text(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("rerun_count", sa.Integer(), nullable=True),
        sa.Column("edit_count", sa.Integer(), nullable=True),
        sa.Column("time_to_accept_ms", sa.Integer(), nullable=True),
        sa.Column("apply_target", sa.String(length=20), nullable=True),
        sa.Column("anti_goal_violations", sa.Integer(), nullable=True),
        sa.Column("coverage_emph_triggered", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_lens_receipts_execution", "lens_receipts", ["execution_id"])
    op.create_index("idx_lens_receipts_workspace", "lens_receipts", ["workspace_id"])
    op.create_index("idx_lens_receipts_hash", "lens_receipts", ["effective_lens_hash"])
    op.create_index("idx_lens_receipts_accepted", "lens_receipts", ["accepted"])
    op.create_index("idx_lens_receipts_apply_target", "lens_receipts", ["apply_target"])

    # --- Preview Votes ---
    op.create_table(
        "preview_votes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preview_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("chosen_variant", sa.String(length=10), nullable=False),
        sa.Column("preview_type", sa.String(length=50), nullable=True),
        sa.Column("input_text_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_preview_votes_workspace", "preview_votes", ["workspace_id"])
    op.create_index("idx_preview_votes_profile", "preview_votes", ["profile_id"])
    op.create_index("idx_preview_votes_session", "preview_votes", ["session_id"])
    op.create_index("idx_preview_votes_chosen", "preview_votes", ["chosen_variant"])


def downgrade() -> None:
    op.drop_index("idx_preview_votes_chosen", table_name="preview_votes")
    op.drop_index("idx_preview_votes_session", table_name="preview_votes")
    op.drop_index("idx_preview_votes_profile", table_name="preview_votes")
    op.drop_index("idx_preview_votes_workspace", table_name="preview_votes")
    op.drop_table("preview_votes")

    op.drop_index("idx_lens_receipts_apply_target", table_name="lens_receipts")
    op.drop_index("idx_lens_receipts_accepted", table_name="lens_receipts")
    op.drop_index("idx_lens_receipts_hash", table_name="lens_receipts")
    op.drop_index("idx_lens_receipts_workspace", table_name="lens_receipts")
    op.drop_index("idx_lens_receipts_execution", table_name="lens_receipts")
    op.drop_table("lens_receipts")

    op.drop_index("idx_lens_snapshots_workspace", table_name="lens_snapshots")
    op.drop_index("idx_lens_snapshots_profile", table_name="lens_snapshots")
    op.drop_index("idx_lens_snapshots_hash", table_name="lens_snapshots")
    op.drop_table("lens_snapshots")

    op.drop_index("idx_workspace_overrides_node", table_name="workspace_lens_overrides")
    op.drop_index("idx_workspace_overrides_ws", table_name="workspace_lens_overrides")
    op.drop_table("workspace_lens_overrides")

    op.drop_index("idx_lens_profile_nodes_node", table_name="lens_profile_nodes")
    op.drop_index("idx_lens_profile_nodes_preset", table_name="lens_profile_nodes")
    op.drop_table("lens_profile_nodes")

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
