"""
LiteLLM client: single entry point for all LLM providers.

Wraps litellm.completion / litellm.embedding so the rest of DVAIA stays
provider-agnostic. Any provider LiteLLM supports (~100+) is reachable:
OpenAI, Gemini, Ollama, Anthropic, Bedrock, Vertex, Groq, OpenRouter, etc.

Model id format: '<provider>/<model>' (LiteLLM canonical).
  openai/gpt-4o-mini
  gemini/gemini-2.0-flash
  ollama/llama3.2
  anthropic/claude-3-5-sonnet-20241022

Backward compatible with the legacy 'provider:model' format and the
'google:' prefix; normalize_model_id() converts them.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import litellm

# Global LiteLLM tuning. Done once at import time.
litellm.drop_params = True
litellm.suppress_debug_info = True

# Bridge legacy GOOGLE_API_KEY → GEMINI_API_KEY (LiteLLM's canonical name).
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]


_PROVIDER_ENV_KEYS: Dict[str, List[str]] = {
    "openai":       ["OPENAI_API_KEY"],
    "gemini":       ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "anthropic":    ["ANTHROPIC_API_KEY"],
    "groq":         ["GROQ_API_KEY"],
    "mistral":      ["MISTRAL_API_KEY"],
    "cohere":       ["COHERE_API_KEY"],
    "openrouter":   ["OPENROUTER_API_KEY"],
    "together_ai":  ["TOGETHER_API_KEY", "TOGETHERAI_API_KEY"],
    "deepseek":     ["DEEPSEEK_API_KEY"],
    "fireworks_ai": ["FIREWORKS_API_KEY", "FIREWORKS_AI_API_KEY"],
    "perplexity":   ["PERPLEXITYAI_API_KEY", "PERPLEXITY_API_KEY"],
    "vertex_ai":    ["VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"],
    "bedrock":      ["AWS_ACCESS_KEY_ID", "AWS_PROFILE"],
    "azure":        ["AZURE_API_KEY", "AZURE_OPENAI_API_KEY"],
    "huggingface":  ["HUGGINGFACE_API_KEY", "HF_TOKEN"],
}

_KNOWN_PROVIDERS = set(_PROVIDER_ENV_KEYS.keys()) | {"ollama", "ollama_chat", "google"}


def normalize_model_id(model_id: Optional[str]) -> str:
    """
    Convert legacy 'provider:model' → 'provider/model'.
    Map 'google:' prefix → 'gemini/'.
    Bare model name (no prefix) → 'ollama/<model>'.

    Preserves Ollama tag colons inside the model part: 'ollama:qwen2.5vl:7b'
    → 'ollama/qwen2.5vl:7b' (the first colon is the provider separator).
    """
    s = (model_id or "").strip()
    if not s:
        return ""
    if "/" in s and s.split("/", 1)[0].lower() in _KNOWN_PROVIDERS:
        head, _, rest = s.partition("/")
        head_lower = head.lower()
        if head_lower == "google":
            return f"gemini/{rest}"
        return f"{head_lower}/{rest}"
    if ":" in s:
        head, _, rest = s.partition(":")
        head_lower = head.lower()
        if head_lower in _KNOWN_PROVIDERS:
            if head_lower == "google":
                return f"gemini/{rest.strip()}"
            return f"{head_lower}/{rest.strip()}" if rest else f"{head_lower}/"
        # Unknown prefix — assume the whole string is an ollama model tag (e.g. "qwen3:0.6b")
        return f"ollama/{s}"
    return f"ollama/{s}"


def detect_provider(model_id: str) -> str:
    """Provider prefix (e.g. 'openai', 'ollama', 'anthropic')."""
    normalized = normalize_model_id(model_id)
    if "/" in normalized:
        return normalized.split("/", 1)[0].lower()
    return "ollama"


def strip_provider(model_id: str) -> str:
    """Bare model name without provider prefix."""
    normalized = normalize_model_id(model_id)
    if "/" in normalized:
        return normalized.split("/", 1)[1].strip()
    return normalized.strip()


def list_available_providers() -> Dict[str, bool]:
    """Map provider name → whether its credentials look configured in env."""
    out: Dict[str, bool] = {}
    for prov, keys in _PROVIDER_ENV_KEYS.items():
        out[prov] = any(os.getenv(k, "").strip() for k in keys)
    out["ollama"] = True
    return out


def supports_vision(model_id: str) -> bool:
    """Best-effort vision-capability check via litellm."""
    try:
        return bool(litellm.supports_vision(model=normalize_model_id(model_id)))
    except Exception:
        return False


def _is_thinking_model(model_id: str) -> bool:
    """qwen3 / deepseek-r1 / o1 family expose chain-of-thought when prompted."""
    s = strip_provider(model_id).lower()
    return (
        s.startswith("qwen3")
        or s.startswith("deepseek-r1")
        or "deepseek-r1" in s
    )


def _completion_kwargs(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Translate options dict to litellm.completion kwargs."""
    out: Dict[str, Any] = {}
    if not options:
        return out
    if options.get("temperature") is not None:
        try:
            out["temperature"] = float(options["temperature"])
        except (TypeError, ValueError):
            pass
    if options.get("top_p") is not None:
        try:
            out["top_p"] = float(options["top_p"])
        except (TypeError, ValueError):
            pass
    if options.get("top_k") is not None:
        try:
            out["top_k"] = int(options["top_k"])
        except (TypeError, ValueError):
            pass
    num = (
        options.get("max_output_tokens")
        or options.get("max_tokens")
        or options.get("num_predict")
    )
    if num is not None:
        try:
            out["max_tokens"] = int(num)
        except (TypeError, ValueError):
            pass
    rp = options.get("repeat_penalty")
    if rp is not None:
        # OpenAI-style frequency_penalty is [-2,2] where >0 discourages repeats.
        # Ollama repeat_penalty is [0,inf) where >1 discourages. Convert roughly.
        try:
            out["frequency_penalty"] = max(-2.0, min(2.0, float(rp) - 1.0))
        except (TypeError, ValueError):
            pass
    return out


def _provider_kwargs(model_id: str) -> Dict[str, Any]:
    """Provider-specific extras (e.g. api_base for ollama)."""
    provider = detect_provider(model_id)
    kw: Dict[str, Any] = {}
    if provider in ("ollama", "ollama_chat"):
        host = os.getenv("OLLAMA_HOST", "").strip().rstrip("/")
        if host:
            kw["api_base"] = host
    return kw


def _extract_text(response: Any) -> Tuple[str, str]:
    """Pull (text, reasoning) from a LiteLLM ModelResponse."""
    try:
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is None and isinstance(choice, dict):
            message = choice.get("message")

        def _get(attr: str) -> Any:
            if message is None:
                return None
            if isinstance(message, dict):
                return message.get(attr)
            return getattr(message, attr, None)

        content = _get("content")
        reasoning_raw = (
            _get("reasoning_content")
            or _get("thinking")
            or ""
        )
        reasoning = str(reasoning_raw).strip() if reasoning_raw else ""

        if isinstance(content, list):
            parts: List[str] = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(str(p.get("text", "")))
                elif isinstance(p, str):
                    parts.append(p)
            return ("\n".join(parts).strip(), reasoning)
        if isinstance(content, str):
            return (content.strip(), reasoning)
    except (AttributeError, IndexError, KeyError, TypeError):
        pass
    return ("", "")


def _build_messages(
    messages: List[Dict[str, str]],
    system_instruction: Optional[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if system_instruction:
        out.append({"role": "system", "content": system_instruction})
    for m in messages or []:
        role = (m.get("role") or "user").strip().lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"
        out.append({"role": role, "content": content})
    return out


def complete(
    model_id: str,
    messages: List[Dict[str, str]],
    *,
    options: Optional[Dict[str, Any]] = None,
    system_instruction: Optional[str] = None,
    timeout: Optional[int] = 120,
) -> Dict[str, str]:
    """Multi-turn completion. Returns {"text", "thinking"}."""
    normalized = normalize_model_id(model_id)
    api_messages = _build_messages(messages, system_instruction)
    if not api_messages:
        return {"text": "No text returned.", "thinking": ""}

    kwargs: Dict[str, Any] = {
        "model": normalized,
        "messages": api_messages,
        "timeout": timeout,
        **_completion_kwargs(options),
        **_provider_kwargs(normalized),
    }
    if _is_thinking_model(normalized):
        kwargs.setdefault("extra_body", {})["think"] = True

    response = litellm.completion(**kwargs)
    text, reasoning = _extract_text(response)
    return {"text": text or "No text returned.", "thinking": reasoning}


def complete_text(
    model_id: str,
    prompt: str,
    *,
    options: Optional[Dict[str, Any]] = None,
    system_instruction: Optional[str] = None,
    timeout: Optional[int] = 120,
) -> Dict[str, str]:
    """Single-turn convenience wrapper."""
    return complete(
        model_id,
        [{"role": "user", "content": prompt or ""}],
        options=options,
        system_instruction=system_instruction,
        timeout=timeout,
    )


def _image_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    mapping = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".gif":  "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
        ".tif": "image/tiff", ".tiff": "image/tiff",
    }
    return mapping.get(path.suffix.lower(), "image/png")


def complete_with_images(
    model_id: str,
    prompt: str,
    image_paths: Iterable[Union[str, Path]],
    *,
    options: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = 120,
) -> Dict[str, str]:
    """Vision: text prompt + local image files. Uses OpenAI-style image_url content blocks."""
    normalized = normalize_model_id(model_id)
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt or ""}]
    added = 0
    for raw in image_paths:
        path = Path(raw)
        if not path.is_file():
            continue
        mime = _image_mime_type(path)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        })
        added += 1
    if added == 0:
        return {"text": "No valid image files provided.", "thinking": ""}

    if not supports_vision(normalized):
        return {
            "text": (
                f"Model {normalized} does not support vision. "
                "Set VISION_MODEL in .env to a vision-capable model "
                "(e.g. ollama/qwen2.5vl:7b, openai/gpt-4o, gemini/gemini-2.0-flash)."
            ),
            "thinking": "",
        }

    kwargs: Dict[str, Any] = {
        "model": normalized,
        "messages": [{"role": "user", "content": content}],
        "timeout": timeout,
        **_completion_kwargs(options),
        **_provider_kwargs(normalized),
    }
    response = litellm.completion(**kwargs)
    text, reasoning = _extract_text(response)
    return {"text": text or "No text returned.", "thinking": reasoning}


_embed_dim_cache: Dict[str, int] = {}


def embed(model_id: str, texts: List[str]) -> List[List[float]]:
    """Embed a list of strings. Returns list of vectors."""
    stripped = [t.strip() for t in (texts or []) if (t or "").strip()]
    if not stripped:
        return []
    normalized = normalize_model_id(model_id)
    kwargs: Dict[str, Any] = {
        "model": normalized,
        "input": stripped,
        **_provider_kwargs(normalized),
    }
    response = litellm.embedding(**kwargs)
    vecs: List[List[float]] = []
    data = getattr(response, "data", None) or response.get("data", [])  # type: ignore[union-attr]
    for item in data or []:
        if isinstance(item, dict):
            vec = item.get("embedding")
        else:
            vec = getattr(item, "embedding", None)
        if vec is not None:
            vecs.append(list(vec))
    if vecs and normalized not in _embed_dim_cache:
        _embed_dim_cache[normalized] = len(vecs[0])
    return vecs


def embedding_dimension(model_id: str) -> Optional[int]:
    """Probe embedding dimension once (cached) by embedding a single token."""
    normalized = normalize_model_id(model_id)
    if normalized in _embed_dim_cache:
        return _embed_dim_cache[normalized]
    try:
        vecs = embed(model_id, ["dimension probe"])
        if vecs:
            return _embed_dim_cache.get(normalized) or len(vecs[0])
    except Exception:
        return None
    return None


def clear_caches() -> None:
    """Reset internal caches (e.g. after API key change)."""
    _embed_dim_cache.clear()
