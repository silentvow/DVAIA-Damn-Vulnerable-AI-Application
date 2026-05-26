"""
LangChain LLM factory: get_llm(model_id) returns a BaseChatModel backed by LiteLLM.

All providers route through ChatLiteLLM, so any LiteLLM-supported provider
(~100+) is available through the same LangChain interface:
  - llm.invoke(messages) for simple calls
  - llm.bind_tools(tools) + ReAct loop for agentic (see app/agent.py)
"""
import warnings
from typing import Any, Optional

warnings.filterwarnings(
    "ignore",
    message=".*Pydantic V1.*Python 3.14.*",
)

from core import litellm_client
from core.config import get_default_model_id, get_ollama_host


def get_llm(
    model_id: Optional[str] = None,
    *,
    timeout: Optional[int] = 120,
    **kwargs: Any,
) -> Any:
    """
    Return a LangChain ChatLiteLLM for the given model_id.

    Accepts legacy 'provider:model' or 'google:...' prefixes; converts to
    LiteLLM's '<provider>/<model>' canonical form.
    """
    resolved = (model_id or get_default_model_id()).strip() or get_default_model_id()
    normalized = litellm_client.normalize_model_id(resolved)
    provider = litellm_client.detect_provider(normalized)

    # Map legacy kwargs to LiteLLM equivalents.
    if "num_predict" in kwargs and "max_tokens" not in kwargs:
        kwargs["max_tokens"] = kwargs.pop("num_predict")
    if "max_output_tokens" in kwargs and "max_tokens" not in kwargs:
        kwargs["max_tokens"] = kwargs.pop("max_output_tokens")
    # Legacy ChatOllama 'reasoning' flag: handled below via extra_body for thinking models.
    kwargs.pop("reasoning", None)

    extra_kwargs: dict = {}

    if provider in ("ollama", "ollama_chat"):
        host = get_ollama_host().rstrip("/")
        if host:
            extra_kwargs["api_base"] = host

    if litellm_client._is_thinking_model(normalized):
        # Ollama: think=true; LiteLLM forwards via extra_body.
        extra_kwargs.setdefault("model_kwargs", {})["extra_body"] = {"think": True}

    try:
        from langchain_litellm import ChatLiteLLM
    except ImportError:
        # Fallback for older deployments shipping langchain-community's wrapper.
        from langchain_community.chat_models import ChatLiteLLM  # type: ignore

    return ChatLiteLLM(
        model=normalized,
        timeout=timeout,
        **extra_kwargs,
        **kwargs,
    )
