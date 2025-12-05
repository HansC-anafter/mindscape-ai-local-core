"""
Constants and default configurations for system settings
"""
DEFAULT_CHAT_MODELS = [
    {
        "model_name": "gpt-5.1-pro",
        "provider": "openai",
        "description": "OpenAI GPT-5.1 Pro (latest, Nov 2025) - Enhanced for writing, data science, business",
        "is_latest": True,
        "is_recommended": True
    },
    {
        "model_name": "gpt-5.1",
        "provider": "openai",
        "description": "OpenAI GPT-5.1 (latest, Nov 2025) - Latest general-purpose model",
        "is_latest": True
    },
    {
        "model_name": "gpt-4o",
        "provider": "openai",
        "description": "OpenAI GPT-4o (updated Mar 2025) - High quality, deprecated Feb 2026",
        "is_deprecated": True,
        "deprecation_date": "2026-02-16"
    },
    {
        "model_name": "gpt-4o-mini",
        "provider": "openai",
        "description": "OpenAI GPT-4o Mini - Cost-effective, 128K context"
    },
    {
        "model_name": "claude-opus-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Opus 4.5 (latest) - Most powerful, enhanced coding & automation",
        "is_latest": True
    },
    {
        "model_name": "claude-haiku-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Haiku 4.5 (latest, Oct 2025) - Fastest, most cost-efficient",
        "is_latest": True
    },
    {
        "model_name": "claude-sonnet-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Sonnet 4.5 (latest) - Balanced performance"
    },
    {
        "model_name": "claude-3.5-sonnet",
        "provider": "anthropic",
        "description": "Anthropic Claude 3.5 Sonnet (deprecated Oct 2025)",
        "is_deprecated": True
    },
    {
        "model_name": "claude-3-haiku",
        "provider": "anthropic",
        "description": "Anthropic Claude 3 Haiku (legacy)"
    },
    {
        "model_name": "gemini-3-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 3 Pro (latest, Nov 2025 preview) - Most capable model, 1M context window",
        "is_latest": True,
        "is_recommended": True,
        "context_window": 1000000
    },
    {
        "model_name": "gemini-2.5-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Pro (stable, Jun 2025) - Enhanced performance and accuracy",
        "is_latest": True,
        "context_window": 2000000
    },
    {
        "model_name": "gemini-2.5-flash",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Flash (stable, Jun 2025) - Fast and efficient",
        "is_latest": True,
        "context_window": 1000000
    },
    {
        "model_name": "gemini-2.5-flash-lite",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Flash-Lite (preview) - Lower cost option",
        "context_window": 1000000
    },
    {
        "model_name": "gemini-1.5-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 1.5 Pro - 2M context window",
        "context_window": 2000000
    },
    {
        "model_name": "gemini-1.5-flash",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 1.5 Flash - Fast and efficient, 1M context window",
        "context_window": 1000000
    },
    {
        "model_name": "gemini-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini Pro (legacy) - General purpose model"
    },
    {
        "model_name": "gemini-pro-vision",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini Pro Vision (legacy) - Multimodal model with vision capabilities"
    }
]

DEFAULT_EMBEDDING_MODELS = [
    {
        "model_name": "text-embedding-3-large",
        "provider": "openai",
        "description": "OpenAI text-embedding-3-large (latest) - 3072 dimensions, best performance",
        "is_latest": True,
        "is_recommended": True,
        "dimensions": 3072
    },
    {
        "model_name": "text-embedding-3-small",
        "provider": "openai",
        "description": "OpenAI text-embedding-3-small - 1536 dimensions, cost-effective",
        "dimensions": 1536
    },
    {
        "model_name": "text-embedding-ada-002",
        "provider": "openai",
        "description": "OpenAI text-embedding-ada-002 (legacy) - 1536 dimensions",
        "is_legacy": True,
        "dimensions": 1536
    },
    {
        "model_name": "text-embedding-004",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini Embedding (latest, Jul 2025) - 768 dimensions, supports 100+ languages, 2048 token input",
        "is_latest": True,
        "is_recommended": True,
        "dimensions": 768
    },
    {
        "model_name": "textembedding-gecko@003",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Text Embedding Gecko 003 (2024) - 768 dimensions, optimized for retrieval",
        "dimensions": 768
    },
    {
        "model_name": "textembedding-gecko-multilingual@001",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Text Embedding Gecko Multilingual (2024) - 768 dimensions, supports 100+ languages",
        "dimensions": 768
    }
]

