"""
Provider configuration — driven entirely by environment variables.

Set LLM_PROVIDER to switch the inference backend.
Set EMBED_PROVIDER (independently) to switch the embedding backend.
Override individual models with LLM_MODEL / EMBED_MODEL.

Switching embedding providers changes the vector dimension and requires
re-seeding the DB: `python fixtures/seed_db.py`.
"""
from __future__ import annotations

import os

# LLM_PROVIDER → default model (litellm model string)
_LLM_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",  # $3/$15 per MTok in/out
    "openai": "gpt-4o-mini",                  # $0.15/$0.60 — 20× cheaper than sonnet
    "groq": "groq/llama-3.3-70b-versatile",   # free tier (rate-limited), fast
    "ollama": "ollama/llama3.2",              # fully local, free, needs Ollama running
}

# EMBED_PROVIDER → default model spec
# Prefix "local/" means sentence-transformers (no network, no API key required).
# All other prefixes are passed to litellm.aembedding().
_EMBED_DEFAULTS: dict[str, str] = {
    "openai": "openai/text-embedding-3-small",  # 1536 dims, $0.02/MTok
    "ollama": "ollama/nomic-embed-text",        # 768 dims, free local
    "local": "local/all-MiniLM-L6-v2",         # 384 dims, free — pip install sentence-transformers
}

SUPPORTED_LLM_PROVIDERS = list(_LLM_DEFAULTS)
SUPPORTED_EMBED_PROVIDERS = list(_EMBED_DEFAULTS)


def get_llm_model() -> str:
    """Return the litellm model string for LLM calls."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider not in _LLM_DEFAULTS:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. Supported: {SUPPORTED_LLM_PROVIDERS}"
        )
    return os.environ.get("LLM_MODEL") or _LLM_DEFAULTS[provider]


def get_embed_model() -> str:
    """
    Return the embedding model spec.
    Format: '<provider>/<model-name>' — e.g. 'openai/text-embedding-3-small'.
    The 'local/' prefix triggers sentence-transformers instead of litellm.
    """
    provider = os.environ.get("EMBED_PROVIDER", "openai").lower()
    if provider not in _EMBED_DEFAULTS:
        raise ValueError(
            f"Unknown EMBED_PROVIDER={provider!r}. Supported: {SUPPORTED_EMBED_PROVIDERS}"
        )
    return os.environ.get("EMBED_MODEL") or _EMBED_DEFAULTS[provider]
