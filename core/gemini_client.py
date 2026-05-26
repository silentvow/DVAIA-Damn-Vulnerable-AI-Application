"""
Backward-compat shim: Gemini is now routed via core.litellm_client.

Kept so existing import sites continue to work during the LiteLLM migration.
Will be removed in a follow-up PR.
"""
from core.litellm_client import clear_caches as _clear_caches


def clear_gemini_client_cache() -> None:
    """Legacy: reset cached client. Now resets LiteLLM-level caches."""
    _clear_caches()


__all__ = ["clear_gemini_client_cache"]
