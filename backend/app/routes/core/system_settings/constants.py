"""
Constants and default configurations for system settings
"""

DEFAULT_CHAT_MODELS = [
    {
        "model_name": "gpt-5.1-pro",
        "provider": "openai",
        "description": "OpenAI GPT-5.1 Pro (latest, Nov 2025) - Enhanced for writing, data science, business",
        "is_latest": True,
        "is_recommended": True,
    },
    {
        "model_name": "gpt-5.1",
        "provider": "openai",
        "description": "OpenAI GPT-5.1 (latest, Nov 2025) - Latest general-purpose model",
        "is_latest": True,
    },
    {
        "model_name": "gpt-4o",
        "provider": "openai",
        "description": "OpenAI GPT-4o (updated Mar 2025) - High quality, deprecated Feb 2026",
        "is_deprecated": True,
        "deprecation_date": "2026-02-16",
    },
    {
        "model_name": "gpt-4o-mini",
        "provider": "openai",
        "description": "OpenAI GPT-4o Mini - Cost-effective, 128K context",
    },
    {
        "model_name": "claude-opus-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Opus 4.5 (latest) - Most powerful, enhanced coding & automation",
        "is_latest": True,
    },
    {
        "model_name": "claude-haiku-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Haiku 4.5 (latest, Oct 2025) - Fastest, most cost-efficient",
        "is_latest": True,
    },
    {
        "model_name": "claude-sonnet-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Sonnet 4.5 (latest) - Balanced performance",
    },
    {
        "model_name": "claude-3.5-sonnet",
        "provider": "anthropic",
        "description": "Anthropic Claude 3.5 Sonnet (deprecated Oct 2025)",
        "is_deprecated": True,
    },
    {
        "model_name": "claude-3-haiku",
        "provider": "anthropic",
        "description": "Anthropic Claude 3 Haiku (legacy)",
    },
    # ── Local deployment (Ollama) ────────────────────────────────────────
    {
        "model_name": "qwen3:8b",
        "provider": "ollama",
        "description": "Qwen 3 8B (Ollama) — Strong instruction following, tool use, multilingual",
        "is_latest": True,
        "is_recommended": True,
    },
    {
        "model_name": "deepseek-r1:8b",
        "provider": "ollama",
        "description": "DeepSeek R1 8B (Ollama) — Reasoning model for complex planning & analysis",
        "is_latest": True,
    },
    {
        "model_name": "llama3.1:8b",
        "provider": "ollama",
        "description": "Meta Llama 3.1 8B (Ollama) — General-purpose, strong writing & reasoning",
        "is_latest": True,
    },
    {
        "model_name": "gemma3:4b",
        "provider": "ollama",
        "description": "Google Gemma 3 4B (Ollama) — Lightweight, fast summarization & Q&A",
        "is_latest": True,
    },
    {
        "model_name": "mistral:7b",
        "provider": "ollama",
        "description": "Mistral 7B (Ollama) — Efficient general-purpose model",
    },
    {
        "model_name": "gemini-3-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 3 Pro (latest, Nov 2025 preview) - Most capable model, 1M context window",
        "is_latest": True,
        "is_recommended": True,
        "context_window": 1000000,
    },
    {
        "model_name": "gemini-2.5-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Pro (stable, Jun 2025) - Enhanced performance and accuracy",
        "is_latest": True,
        "context_window": 2000000,
    },
    {
        "model_name": "gemini-2.5-flash",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Flash (stable, Jun 2025) - Fast and efficient",
        "is_latest": True,
        "context_window": 1000000,
    },
    {
        "model_name": "gemini-2.5-flash-lite",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 2.5 Flash-Lite (preview) - Lower cost option",
        "context_window": 1000000,
    },
    {
        "model_name": "gemini-1.5-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 1.5 Pro - 2M context window",
        "context_window": 2000000,
    },
    {
        "model_name": "gemini-1.5-flash",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini 1.5 Flash - Fast and efficient, 1M context window",
        "context_window": 1000000,
    },
    {
        "model_name": "gemini-pro",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini Pro (legacy) - General purpose model",
    },
    {
        "model_name": "gemini-pro-vision",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Gemini Pro Vision (legacy) - Multimodal model with vision capabilities",
    },
]

DEFAULT_EMBEDDING_MODELS = [
    {
        "model_name": "text-embedding-3-large",
        "provider": "openai",
        "description": "OpenAI text-embedding-3-large (latest) - 3072 dimensions, best performance",
        "is_latest": True,
        "is_recommended": True,
        "dimensions": 3072,
    },
    {
        "model_name": "text-embedding-3-small",
        "provider": "openai",
        "description": "OpenAI text-embedding-3-small - 1536 dimensions, cost-effective",
        "dimensions": 1536,
    },
    {
        "model_name": "text-embedding-ada-002",
        "provider": "openai",
        "description": "OpenAI text-embedding-ada-002 (legacy) - 1536 dimensions",
        "is_legacy": True,
        "dimensions": 1536,
    },
    {
        "model_name": "gemini-embedding-001",
        "provider": "gemini-api",
        "description": "Google Gemini Embedding (latest) - 3072 dimensions, free tier available, supports 100+ languages, 2048 token input",
        "is_latest": True,
        "is_recommended": True,
        "dimensions": 3072,
    },
    {
        "model_name": "text-embedding-004",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Text Embedding 004 (deprecated, use gemini-embedding-001) - 768 dimensions",
        "is_deprecated": True,
        "is_legacy": True,
        "dimensions": 768,
    },
    {
        "model_name": "textembedding-gecko@003",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Text Embedding Gecko 003 (2024) - 768 dimensions, optimized for retrieval",
        "dimensions": 768,
    },
    {
        "model_name": "textembedding-gecko-multilingual@001",
        "provider": "vertex-ai",
        "description": "Google Vertex AI Text Embedding Gecko Multilingual (2024) - 768 dimensions, supports 100+ languages",
        "dimensions": 768,
    },
]

DEFAULT_MULTIMODAL_MODELS = [
    # ── Cloud providers ──────────────────────────────────────────────────
    {
        "model_name": "gpt-4o",
        "provider": "openai",
        "description": "OpenAI GPT-4o — Vision + text, 128K context",
        "is_latest": True,
        "is_recommended": True,
        "context_window": 128000,
    },
    {
        "model_name": "gpt-4o-mini",
        "provider": "openai",
        "description": "OpenAI GPT-4o Mini — Vision + text, cost-effective",
        "context_window": 128000,
    },
    {
        "model_name": "claude-sonnet-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Sonnet 4.5 — Vision + text, balanced",
        "is_latest": True,
    },
    {
        "model_name": "claude-haiku-4.5",
        "provider": "anthropic",
        "description": "Anthropic Claude Haiku 4.5 — Vision + text, fast & cheap",
        "is_latest": True,
    },
    {
        "model_name": "gemini-2.5-pro",
        "provider": "vertex-ai",
        "description": "Google Gemini 2.5 Pro — Vision + text + audio, 2M context",
        "is_latest": True,
        "is_recommended": True,
        "context_window": 2000000,
    },
    {
        "model_name": "gemini-2.5-flash",
        "provider": "vertex-ai",
        "description": "Google Gemini 2.5 Flash — Vision + text, fast & efficient",
        "is_latest": True,
        "context_window": 1000000,
    },
    # ── Local deployment ─────────────────────────────────────────────────
    {
        "model_name": "llama3.2-vision",
        "provider": "ollama",
        "description": "Llama 3.2 Vision (Ollama) — Meta's latest vision model, 11B/90B, strong OCR & reasoning",
        "is_latest": True,
        "is_recommended": True,
    },
    {
        "model_name": "qwen2.5vl",
        "provider": "ollama",
        "description": "Qwen 2.5 VL (Ollama) — Alibaba's vision-language model, strong multilingual & document understanding",
        "is_latest": True,
    },
    {
        "model_name": "llava",
        "provider": "ollama",
        "description": "LLaVA (Ollama) — Open-source vision-language model, runs locally (legacy)",
    },
    {
        "model_name": "gemma3:12b",
        "provider": "ollama",
        "description": "Google Gemma 3 12B (Ollama) — Vision + text, 1080p image understanding, multilingual",
        "is_latest": True,
        "is_recommended": True,
    },
    {
        "model_name": "mistral-small3.1",
        "provider": "ollama",
        "description": "Mistral Small 3.1 (Ollama) — Vision + text, enhanced long context",
        "is_latest": True,
    },
    {
        "model_name": "llama4-scout",
        "provider": "ollama",
        "description": "Meta Llama 4 Scout (Ollama) — Multimodal reasoning, latest Meta vision model",
        "is_latest": True,
    },
    {
        "model_name": "moondream:1.8b",
        "provider": "ollama",
        "description": "Moondream 1.8B (Ollama) — Ultra-lightweight vision model, efficient for edge devices",
    },
]
