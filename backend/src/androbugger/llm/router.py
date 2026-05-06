"""Provider-agnostic LLM router via LiteLLM."""
import asyncio
import logging
import time
from typing import AsyncGenerator

import litellm

from androbugger.config import settings
from androbugger.llm.models import LLMResponse

logger = logging.getLogger(__name__)

litellm.set_verbose = False


def _model_str(model: str | None) -> str:
    if model:
        return model
    return settings.default_llm_model


def is_local_provider(model: str) -> bool:
    return model.startswith("ollama/") or model.startswith("ollama_chat/")


async def complete(
    messages: list[dict],
    model: str | None = None,
    user_id: str | None = None,
    device_serial: str | None = None,
) -> LLMResponse:
    model_id = _model_str(model)
    start = time.monotonic()

    # Build extra kwargs for Ollama
    extra: dict = {}
    if is_local_provider(model_id):
        extra["api_base"] = settings.ollama_base_url

    try:
        resp = await litellm.acompletion(
            model=model_id,
            messages=messages,
            max_tokens=settings.llm_max_tokens,
            **extra,
        )
        elapsed = (time.monotonic() - start) * 1000
        content = resp.choices[0].message.content or ""
        usage = resp.usage or {}
        cost = litellm.completion_cost(completion_response=resp) if not is_local_provider(model_id) else None
        return LLMResponse(
            content=content,
            provider=model_id.split("/")[0],
            model=model_id,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            latency_ms=elapsed,
            cost_usd=cost,
        )
    except Exception as exc:
        logger.warning("Primary model %s failed: %s — trying fallback", model_id, exc)
        # Fallback
        fallback = settings.fallback_llm_model
        if fallback == model_id:
            raise
        extra_fb: dict = {}
        if is_local_provider(fallback):
            extra_fb["api_base"] = settings.ollama_base_url
        resp = await litellm.acompletion(
            model=fallback,
            messages=messages,
            max_tokens=settings.llm_max_tokens,
            **extra_fb,
        )
        elapsed = (time.monotonic() - start) * 1000
        content = resp.choices[0].message.content or ""
        usage = resp.usage or {}
        return LLMResponse(
            content=content,
            provider=fallback.split("/")[0],
            model=fallback,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            latency_ms=elapsed,
            cost_usd=None,
        )


async def stream(
    messages: list[dict],
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    model_id = _model_str(model)
    extra: dict = {}
    if is_local_provider(model_id):
        extra["api_base"] = settings.ollama_base_url

    response = await litellm.acompletion(
        model=model_id,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        stream=True,
        **extra,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
