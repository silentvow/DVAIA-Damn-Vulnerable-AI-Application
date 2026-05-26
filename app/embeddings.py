"""
RAG embedding service via LiteLLM.

A single embedding model is configured globally through EMBEDDING_MODEL in
.env (LiteLLM canonical 'provider/model' form; bare names default to ollama/).

The embedding model is independent of the chat provider — e.g. chat with
openai/gpt-4o while embedding with ollama/nomic-embed-text. The Qdrant
collection name is derived from the embedding model id and its vector
dimension so swapping models doesn't pollute an existing collection.
"""
from typing import List, Optional

from core import litellm_client
from core.config import get_embedding_model_id


def _sanitize(s: str) -> str:
    """Make a string safe for use inside a Qdrant collection name."""
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s)


def current_embedding_model() -> str:
    """
    LiteLLM-canonical embedding model id (e.g. ollama/nomic-embed-text).
    Empty string when RAG is disabled (EMBEDDING_MODEL=none / unset).
    """
    raw = get_embedding_model_id()
    if not raw:
        return ""
    return litellm_client.normalize_model_id(raw)


def rag_enabled() -> bool:
    """True when an embedding model is configured."""
    return bool(current_embedding_model())


def current_embedding_dimension() -> Optional[int]:
    """Vector size of the current embedding model. Probed once on first use."""
    model = current_embedding_model()
    if not model:
        return None
    return litellm_client.embedding_dimension(model)


def current_collection_name() -> str:
    """
    Qdrant collection for RAG chunks at the current embedding model.
    Format: rag_chunks__<provider>__<model>__<dim>.
    Returns a 'disabled' sentinel when no embedding model is configured.
    """
    model_id = current_embedding_model()
    if not model_id:
        return "rag_chunks__disabled"
    provider = litellm_client.detect_provider(model_id)
    model_name = litellm_client.strip_provider(model_id)
    slug = _sanitize(f"{provider}__{model_name}")
    dim = current_embedding_dimension()
    if dim:
        return f"rag_chunks__{slug}__{dim}"
    return f"rag_chunks__{slug}"


def embed_text(text: str, llm_provider: Optional[str] = None) -> List[float]:
    """
    Embed one string. Returns [] if RAG is disabled or text is empty.
    llm_provider param is accepted for back-compat but ignored.
    """
    if not (text or "").strip():
        return []
    model = current_embedding_model()
    if not model:
        return []
    vecs = litellm_client.embed(model, [text.strip()])
    return vecs[0] if vecs else []


def embed_texts(texts: List[str], llm_provider: Optional[str] = None) -> List[List[float]]:
    """Embed multiple strings. Returns [] if RAG is disabled or input is empty."""
    stripped = [t.strip() for t in (texts or []) if (t or "").strip()]
    if not stripped:
        return []
    model = current_embedding_model()
    if not model:
        return []
    return litellm_client.embed(model, stripped)


def clear_embeddings_cache() -> None:
    """Reset cached embedding-dim probe (e.g. after model change)."""
    litellm_client.clear_caches()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Returns 0 for empty / zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
