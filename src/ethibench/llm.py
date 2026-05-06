"""LLM provider factory — supports OpenAI, Anthropic, Ollama, and Gemini."""

import os

import pydantic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


def get_model(
    model_name: str,
    provider: str,
    api_url: str | None = None,
    temperature: float = 0.5,
) -> BaseChatModel:
    """Create a LangChain chat model for the given provider.

    Args:
        model_name: Model identifier (e.g. "claude-haiku-4-5", "gpt-4o").
        provider: One of "openai", "anthropic", "ollama", "gemini".
        api_url: Optional custom API endpoint (used for Ollama or OpenAI-compatible APIs).
        temperature: Sampling temperature.

    Returns:
        A LangChain BaseChatModel instance.
    """
    if provider == "ollama":
        return ChatOllama(
            name=model_name,
            base_url=api_url or "http://localhost:11434/",
            model=model_name,
            temperature=temperature,
            num_ctx=12000,
        )

    elif provider == "openai":
        if api_url:
            return ChatOpenAI(
                name=model_name,
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=api_url,
                model=model_name,
                temperature=temperature,
            )
        return ChatOpenAI(
            name=model_name,
            model=model_name,
            max_retries=2,
            temperature=temperature,
            seed=42,
            timeout=300,
        )

    elif provider == "anthropic":
        return ChatAnthropic(
            name=model_name,
            api_key=pydantic.SecretStr(os.getenv("ANTHROPIC_API_KEY") or ""),
            model_name=model_name,
            temperature=temperature,
            max_tokens_to_sample=8192,
        )

    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            name=model_name,
            api_key=pydantic.SecretStr(os.getenv("GEMINI_API_KEY") or ""),
            model=model_name,
            max_retries=2,
            temperature=temperature,
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider!r}")
