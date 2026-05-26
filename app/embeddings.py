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
    """LiteLLM-canonical embedding model id (e.g. ollama/nomic-embed-text)."""
    return litellm_client.normalize_model_id(get_embedding_model_id())


def current_embedding_dimension() -> Optional[int]:
    """Vector size of the current embedding model. Probed once on first use."""
    return litellm_client.embedding_dimension(current_embedding_model())


def current_collection_name() -> str:
    """
    Qdrant collection for RAG chunks at the current embedding model.
    Format: rag_chunks__<provider>__<model>__<dim>.
    Omits the dim suffix when probing failed (offline / model not ready).
    """
    model_id = current_embedding_model()
    provider = litellm_client.detect_provider(model_id)
    model_name = litellm_client.strip_provider(model_id)
    slug = _sanitize(f"{provider}__{model_name}")
    dim = current_embedding_dimension()
    if dim:
        return f"rag_chunks__{slug}__{dim}"
    return f"rag_chunks__{slug}"


def embed_text(text: str, llm_provider: Optional[str] = None) -> List[float]:
    """
    Embed one string.
    llm_provider param is accepted for back-compat but ignored — the embedding
    model is configured globally and is independent of the chat provider.
    """
    if not (text or "").strip():
        return []
    vecs = litellm_client.embed(current_embedding_model(), [text.strip()])
    return vecs[0] if vecs else []


def embed_texts(texts: List[str], llm_provider: Optional[str] = None) -> List[List[float]]:
    """Embed multiple strings. llm_provider accepted for back-compat but ignored."""
    stripped = [t.strip() for t in (texts or []) if (t or "").strip()]
    if not stripped:
        return []
    return litellm_client.embed(current_embedding_model(), stripped)


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
