"""
Provider helpers: parse / detect / list LLM providers through LiteLLM.

Backward-compatible: accepts both legacy 'provider:model' and LiteLLM 'provider/model'.
detect_provider() returns the provider prefix as a string (no longer limited to
ollama/gemini/openai — any LiteLLM-supported provider is returned).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from core import litellm_client
from core.config import (
    get_agentic_model_id,
    get_default_model_id,
    get_vision_model_id,
)

# Curated default models per provider — used to seed the UI provider dropdown.
# Override per provider with env var LITELLM_MODELS_<PROVIDER> (comma-separated).
_DEFAULT_MODELS: Dict[str, List[str]] = {
    "openai":       ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "o1-mini"],
    "gemini":       ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "ollama":       ["llama3.2", "qwen3:0.6b", "qwen2.5vl:7b", "nomic-embed-text"],
    "anthropic":    ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "groq":         ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"],
    "mistral":      ["mistral-large-latest", "mistral-small-latest"],
    "cohere":       ["command-r-plus", "command-r"],
    "openrouter":   ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
    "deepseek":     ["deepseek-chat", "deepseek-reasoner"],
    "together_ai":  ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"],
    "fireworks_ai": ["accounts/fireworks/models/llama-v3p1-70b-instruct"],
    "perplexity":   ["llama-3.1-sonar-large-128k-online"],
}


def detect_provider(model_id: str) -> str:
    """Provider prefix (e.g. 'openai', 'ollama', 'anthropic', 'gemini')."""
    return litellm_client.detect_provider(model_id)


def strip_provider_prefix(model_id: str) -> str:
    """Bare model name without provider prefix. Legacy alias kept for callers."""
    return litellm_client.strip_provider(model_id)


def normalize_model_id(model_id: str) -> str:
    """Convert legacy 'provider:model' to LiteLLM 'provider/model'."""
    return litellm_client.normalize_model_id(model_id)


def _curated_models(provider: str) -> List[str]:
    env_key = f"LITELLM_MODELS_{provider.upper()}"
    raw = os.getenv(env_key, "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(_DEFAULT_MODELS.get(provider, []))


def providers_payload() -> Dict[str, Any]:
    """List of providers with availability + curated model list. Drives the UI provider dropdown."""
    avail = litellm_client.list_available_providers()
    providers = sorted(set(list(_DEFAULT_MODELS.keys()) + list(avail.keys())))
    out: Dict[str, Any] = {}
    for prov in providers:
        out[prov] = {
            "available": bool(avail.get(prov, False)),
            "models": _curated_models(prov),
        }
    return out


def resolve_models_for_provider(provider: str) -> Dict[str, Any]:
    """
    Legacy facade: return chat/vision/agentic model_ids for a given provider prefix.

    Picks each role from env (DEFAULT_MODEL / VISION_MODEL / AGENTIC_MODEL).
    If the env model already targets this provider, return it; else fall back
    to the first curated model under that provider.

    embedding_backend is kept for legacy callers; PR 2 replaces this with the
    embedding model id directly.
    """
    p = (provider or "").strip().lower()
    if p == "google":
        p = "gemini"

    def _for_role(env_id: str) -> str:
        normalized = litellm_client.normalize_model_id(env_id)
        if normalized.startswith(f"{p}/"):
            return normalized
        models = _curated_models(p)
        if models:
            return f"{p}/{models[0]}"
        return normalized

    avail = litellm_client.list_available_providers().get(p, False)
    return {
        "available": bool(avail),
        "chat":   _for_role(get_default_model_id()),
        "vision": _for_role(get_vision_model_id()),
        "agentic": _for_role(get_agentic_model_id()),
        "embedding_backend": p,
    }
