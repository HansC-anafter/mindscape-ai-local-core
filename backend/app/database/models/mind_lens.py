from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.database.base import Base
from datetime import datetime


class MindLensSchemaModel(Base):
    __tablename__ = "mind_lens_schemas"

    schema_id = Column(String, primary_key=True)
    role = Column(String, nullable=False)
    label = Column(String)
    dimensions = Column(JSONB, nullable=False)  # JSON structure
    version = Column(String, default="0.1")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    __table_args__ = (Index("idx_mind_lens_schemas_role", "role"),)


class LensSpecModel(Base):
    __tablename__ = "lens_specs"

    lens_id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    category = Column(String, nullable=False)
    applies_to = Column(JSONB, nullable=False)  # List of strings
    inject = Column(JSONB, nullable=False)  # Dict
    params_schema = Column(JSONB)  # Dict
    transformers = Column(JSONB)  # List of strings
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    __table_args__ = (Index("idx_lens_specs_category", "category"),)


class MindLensInstanceModel(Base):
    __tablename__ = "mind_lens_instances"

    mind_lens_id = Column(String, primary_key=True)
    schema_id = Column(String, nullable=False)
    owner_user_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    label = Column(String)
    description = Column(String)
    values = Column(JSONB, nullable=False)  # Dict
    source = Column(JSONB)  # Dict
    version = Column(String, default="0.1")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    __table_args__ = (
        Index("idx_mind_lens_instances_owner", "owner_user_id"),
        Index("idx_mind_lens_instances_role", "role"),
        Index("idx_mind_lens_instances_schema", "schema_id"),
    )
