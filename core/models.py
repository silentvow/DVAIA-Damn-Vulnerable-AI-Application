"""
Model facade: generate() / generate_with_images() for any LiteLLM-supported provider.

Thin wrapper around core.litellm_client. Existing callers keep the same signatures.
model_id format:
  - 'openai/gpt-4o-mini'
  - 'gemini/gemini-2.0-flash'
  - 'ollama/llama3.2'
  - 'anthropic/claude-3-5-sonnet-20241022'
  - any LiteLLM-supported '<provider>/<model>'.

Legacy formats 'provider:model' and 'google:...' are accepted and normalized.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

warnings.filterwarnings(
    "ignore",
    message=".*Pydantic V1.*Python 3.14.*",
)

from core.config import DEFAULT_MODEL
from core import litellm_client


def generate(
    prompt: Optional[str] = None,
    model_id: Optional[str] = DEFAULT_MODEL,
    options: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, str]:
    """
    Single-turn (prompt) or multi-turn (messages) completion.
    options: temperature, top_p, top_k, max_tokens / num_predict / max_output_tokens, repeat_penalty.
    Returns {"text": str, "thinking": str}.
    """
    resolved = model_id or DEFAULT_MODEL
    if messages:
        return litellm_client.complete(resolved, messages, options=options)
    return litellm_client.complete_text(resolved, prompt or "", options=options)


def generate_with_images(
    prompt: str,
    image_paths: List[Union[str, Path]],
    model_id: Optional[str] = DEFAULT_MODEL,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Vision: text prompt + local image files. Returns {"text", "thinking"}."""
    resolved = model_id or DEFAULT_MODEL
    return litellm_client.complete_with_images(resolved, prompt, image_paths, options=options)
