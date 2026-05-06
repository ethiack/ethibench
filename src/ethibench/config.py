"""Configuration from environment variables."""

import os


def get_llm_provider() -> str:
    return os.getenv("ETHIBENCH_LLM_PROVIDER", "openai")


def get_llm_model() -> str:
    return os.getenv("ETHIBENCH_LLM_MODEL", "gpt-5.4-mini")


def get_temperature() -> float:
    return float(os.getenv("ETHIBENCH_TEMPERATURE", "0.3"))


def get_api_url() -> str | None:
    return os.getenv("ETHIBENCH_API_URL", None)


def get_concurrency() -> int:
    return int(os.getenv("ETHIBENCH_CONCURRENCY", "50"))


def get_max_retries() -> int:
    return int(os.getenv("ETHIBENCH_MAX_RETRIES", "5"))


def get_max_parallel_runs() -> int:
    return int(os.getenv("ETHIBENCH_MAX_PARALLEL_RUNS", "3"))
