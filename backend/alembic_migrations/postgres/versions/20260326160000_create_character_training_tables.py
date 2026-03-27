"""create character training tables

Revision ID: 20260326160000
Revises:
Create Date: 2026-03-26 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260326160000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("character_training",)
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _table_exists(inspector, "character_candidates"):
        op.create_table(
            "character_candidates",
            sa.Column("candidate_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.Text, nullable=False),
            sa.Column("source_kind", sa.Text, nullable=False, server_default="manual_upload"),
            sa.Column("status", sa.Text, nullable=False, server_default="draft"),
            sa.Column("persona_summary", sa.Text),
            sa.Column("visual_identity_summary", sa.Text),
            sa.Column("source_refs_json", postgresql.JSONB),
            sa.Column("ethics_policy_state_json", postgresql.JSONB),
            sa.Column("metadata_json", postgresql.JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if not _index_exists(inspector, "character_candidates", "idx_character_candidates_workspace"):
        op.create_index(
            "idx_character_candidates_workspace",
            "character_candidates",
            ["workspace_id"],
        )
    if not _index_exists(inspector, "character_candidates", "idx_character_candidates_status"):
        op.create_index(
            "idx_character_candidates_status",
            "character_candidates",
            ["status"],
        )

    if not _table_exists(inspector, "character_role_fit_scores"):
        op.create_table(
            "character_role_fit_scores",
            sa.Column("score_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("role_id", sa.Text, nullable=False),
            sa.Column("role_label", sa.Text),
            sa.Column("fit_score", sa.Float, nullable=False),
            sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
            sa.Column("decision", sa.Text, nullable=False, server_default="shortlist"),
            sa.Column("reasoning_summary", sa.Text, nullable=False, server_default=""),
            sa.Column("risk_flags_json", postgresql.JSONB),
            sa.Column("role_requirement_snapshot_json", postgresql.JSONB),
            sa.Column("metadata_json", postgresql.JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["character_candidates.candidate_id"],
                ondelete="CASCADE",
            ),
        )
    for index_name, columns in (
        ("idx_character_role_fit_scores_candidate", ["candidate_id"]),
        ("idx_character_role_fit_scores_role", ["role_id"]),
    ):
        if not _index_exists(inspector, "character_role_fit_scores", index_name):
            op.create_index(index_name, "character_role_fit_scores", columns)

    if not _table_exists(inspector, "character_dataset_versions"):
        op.create_table(
            "character_dataset_versions",
            sa.Column("dataset_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("dataset_kind", sa.Text, nullable=False, server_default="reference_only"),
            sa.Column("status", sa.Text, nullable=False, server_default="draft"),
            sa.Column("source_refs_json", postgresql.JSONB),
            sa.Column("prepared_assets_json", postgresql.JSONB),
            sa.Column("mask_policy_json", postgresql.JSONB),
            sa.Column("crop_policy_json", postgresql.JSONB),
            sa.Column("caption_policy_json", postgresql.JSONB),
            sa.Column("quality_report_json", postgresql.JSONB),
            sa.Column("provenance_json", postgresql.JSONB),
            sa.Column("metadata_json", postgresql.JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["character_candidates.candidate_id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("candidate_id", "version", name="uq_character_dataset_versions_candidate_version"),
        )
    for index_name, columns in (
        ("idx_character_dataset_versions_candidate", ["candidate_id"]),
        ("idx_character_dataset_versions_status", ["status"]),
    ):
        if not _index_exists(inspector, "character_dataset_versions", index_name):
            op.create_index(index_name, "character_dataset_versions", columns)

    if not _table_exists(inspector, "character_training_jobs"):
        op.create_table(
            "character_training_jobs",
            sa.Column("job_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("dataset_id", sa.String(length=64), nullable=False),
            sa.Column("trainer_backend", sa.Text, nullable=False),
            sa.Column("model_family", sa.Text, nullable=False),
            sa.Column("training_mode", sa.Text, nullable=False, server_default="lora"),
            sa.Column("base_model_ref", sa.Text, nullable=False),
            sa.Column("status", sa.Text, nullable=False, server_default="queued"),
            sa.Column("progress", sa.Float, nullable=False, server_default="0"),
            sa.Column("config_snapshot_json", postgresql.JSONB),
            sa.Column("evaluation_report_json", postgresql.JSONB),
            sa.Column("error_message", sa.Text),
            sa.Column("runner_ref", sa.Text),
            sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["character_candidates.candidate_id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["dataset_id"],
                ["character_dataset_versions.dataset_id"],
                ondelete="CASCADE",
            ),
        )
    for index_name, columns in (
        ("idx_character_training_jobs_candidate", ["candidate_id"]),
        ("idx_character_training_jobs_dataset", ["dataset_id"]),
        ("idx_character_training_jobs_status", ["status"]),
    ):
        if not _index_exists(inspector, "character_training_jobs", index_name):
            op.create_index(index_name, "character_training_jobs", columns)

    if not _table_exists(inspector, "character_artifacts"):
        op.create_table(
            "character_artifacts",
            sa.Column("artifact_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("job_id", sa.String(length=64)),
            sa.Column("artifact_kind", sa.Text, nullable=False),
            sa.Column("model_family", sa.Text, nullable=False, server_default="agnostic"),
            sa.Column("storage_ref", sa.Text, nullable=False),
            sa.Column("sha256", sa.Text),
            sa.Column("version_label", sa.Text, nullable=False, server_default=""),
            sa.Column("metadata_json", postgresql.JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["character_candidates.candidate_id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["job_id"],
                ["character_training_jobs.job_id"],
                ondelete="SET NULL",
            ),
        )
    for index_name, columns in (
        ("idx_character_artifacts_candidate", ["candidate_id"]),
        ("idx_character_artifacts_job", ["job_id"]),
        ("idx_character_artifacts_kind", ["artifact_kind"]),
    ):
        if not _index_exists(inspector, "character_artifacts", index_name):
            op.create_index(index_name, "character_artifacts", columns)

    if not _table_exists(inspector, "character_packages"):
        op.create_table(
            "character_packages",
            sa.Column("package_id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("candidate_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.Text, nullable=False, server_default="draft"),
            sa.Column("default_display_name", sa.Text, nullable=False),
            sa.Column("supported_families_json", postgresql.JSONB),
            sa.Column("recommended_use_modes_json", postgresql.JSONB),
            sa.Column("render_binding_presets_json", postgresql.JSONB),
            sa.Column("safety_notes_json", postgresql.JSONB),
            sa.Column("metadata_json", postgresql.JSONB),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["character_candidates.candidate_id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("candidate_id", "version", name="uq_character_packages_candidate_version"),
        )
    for index_name, columns in (
        ("idx_character_packages_candidate", ["candidate_id"]),
        ("idx_character_packages_status", ["status"]),
        ("idx_character_packages_workspace", ["workspace_id"]),
    ):
        if not _index_exists(inspector, "character_packages", index_name):
            op.create_index(index_name, "character_packages", columns)

    if not _table_exists(inspector, "character_package_artifacts"):
        op.create_table(
            "character_package_artifacts",
            sa.Column("link_id", sa.String(length=64), primary_key=True),
            sa.Column("package_id", sa.String(length=64), nullable=False),
            sa.Column("artifact_id", sa.String(length=64), nullable=False),
            sa.Column("role_in_package", sa.Text, nullable=False, server_default="included_artifact"),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("binding_metadata_json", postgresql.JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["package_id"],
                ["character_packages.package_id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["artifact_id"],
                ["character_artifacts.artifact_id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "package_id",
                "artifact_id",
                "role_in_package",
                name="uq_character_package_artifacts_link",
            ),
        )
    for index_name, columns in (
        ("idx_character_package_artifacts_package", ["package_id"]),
        ("idx_character_package_artifacts_artifact", ["artifact_id"]),
    ):
        if not _index_exists(inspector, "character_package_artifacts", index_name):
            op.create_index(index_name, "character_package_artifacts", columns)


def downgrade() -> None:
    pass
