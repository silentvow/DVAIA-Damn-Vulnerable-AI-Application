"""
App-level config from environment. No Flask coupling.
Load .env in api/__main__.py; app reads os.getenv.
"""
import os
from pathlib import Path
from typing import Optional


def get_database_uri() -> str:
    """SQLite path for app DB. Default: project root / data / app.db."""
    uri = os.getenv("DATABASE_URI", "")
    if uri:
        return uri
    root = Path(__file__).resolve().parent.parent
    data = root / "data"
    data.mkdir(exist_ok=True)
    return str(data / "app.db")


def get_secret_key() -> str:
    """Flask SECRET_KEY for sessions. Default: fixed dev key (set in prod)."""
    return os.getenv("SECRET_KEY", "dev-secret-change-in-production")


def get_upload_dir() -> str:
    """Directory for uploaded files. Default: project root / data / uploads."""
    path = os.getenv("UPLOAD_DIR", "")
    if path:
        return path
    root = Path(__file__).resolve().parent.parent
    uploads = root / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return str(uploads)


def get_mfa_issuer() -> str:
    """Optional MFA issuer name for display."""
    return os.getenv("MFA_ISSUER", "RedTeamApp")


def get_qdrant_mode() -> str:
    """
    Qdrant storage mode: 'local' (embedded, in-process, no Docker required) or
    'server' (separate Qdrant service).

    Defaults to 'local' unless QDRANT_URL or QDRANT_HOST is explicitly set
    (then 'server'), so first-time users don't need Docker for RAG.
    Override with QDRANT_MODE=local|server.
    """
    mode = os.getenv("QDRANT_MODE", "").strip().lower()
    if mode in ("local", "server"):
        return mode
    if os.getenv("QDRANT_URL", "").strip() or os.getenv("QDRANT_HOST", "").strip():
        return "server"
    return "local"


def get_qdrant_path() -> str:
    """Local-mode storage path. QDRANT_PATH; default: project root / data / qdrant."""
    val = os.getenv("QDRANT_PATH", "").strip()
    if val:
        return val
    root = Path(__file__).resolve().parent.parent
    out = root / "data" / "qdrant"
    out.parent.mkdir(parents=True, exist_ok=True)
    return str(out)


def get_qdrant_url() -> str:
    """Qdrant server URL. When QDRANT_HOST is set (e.g. by Docker), use http://QDRANT_HOST:port so .env cannot override with localhost."""
    host = os.getenv("QDRANT_HOST", "").strip()
    if host:
        port = os.getenv("QDRANT_PORT", "6333").strip()
        return f"http://{host}:{port}"
    return os.getenv("QDRANT_URL", "http://localhost:6333").strip()


def get_qdrant_collection_override() -> Optional[str]:
    """
    When QDRANT_COLLECTION is set, that one collection is used for all RAG ops
    (back-compat / single-collection mode). Otherwise the collection name is
    derived from the embedding model id + dimension by app.embeddings.
    """
    val = os.getenv("QDRANT_COLLECTION", "").strip()
    return val or None


def get_qdrant_collection() -> str:
    """
    Legacy alias. Returns the override if set, else falls through to the
    embedding-model-derived collection from app.embeddings.

    Prefer get_qdrant_collection_override() + app.embeddings.current_collection_name()
    directly in new code.
    """
    explicit = get_qdrant_collection_override()
    if explicit:
        return explicit
    try:
        from app import embeddings as app_embeddings

        return app_embeddings.current_collection_name()
    except Exception:
        return "rag_chunks"


def get_qdrant_collection_for_provider(llm_provider: Optional[str] = None) -> str:
    """
    Legacy alias kept for older imports. llm_provider is ignored — embedding
    model (and therefore collection name) is global, independent of the chat
    provider.
    """
    return get_qdrant_collection()


def get_qdrant_api_key() -> Optional[str]:
    """Optional Qdrant API key (e.g. for Qdrant Cloud)."""
    val = os.getenv("QDRANT_API_KEY", "").strip()
    return val if val else None
