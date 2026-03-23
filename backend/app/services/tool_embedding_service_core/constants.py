"""Constants for ToolEmbeddingService."""

RAG_HIT = "hit"
RAG_MISS = "miss"
RAG_ERROR = "error"

NOMIC_MODELS = {"nomic-embed-text", "nomic-embed-text-v1.5"}
EMBED_MODEL_KEYWORDS = ("embed", "bge", "nomic", "e5", "gte")
DEFAULT_OLLAMA_CANDIDATES = (
    "http://host.docker.internal:11434",
    "http://ollama:11434",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_embeddings (
    id              SERIAL PRIMARY KEY,
    tool_id         TEXT NOT NULL,
    display_name    TEXT,
    description     TEXT NOT NULL,
    category        TEXT,
    capability_code TEXT,
    embedding       vector,
    embedding_model TEXT NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    affordance      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tool_id, embedding_model)
);
"""
