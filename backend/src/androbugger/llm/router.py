"""Provider-agnostic LLM router via LiteLLM with Privacy Gate integration."""
import json
import logging
import time
from collections.abc import AsyncGenerator

import litellm

from androbugger.config import settings
from androbugger.llm.models import LLMResponse

logger = logging.getLogger(__name__)

litellm.set_verbose = False

# Cache of provider_type → full provider config (endpoint, api_key, auth_header,
# temperature, top_p, extra_params). Loaded from DB on startup and refreshed on
# admin changes via refresh_provider_cache().
_provider_cache: dict[str, dict] = {}


def refresh_provider_cache(providers: list[dict]) -> None:
    global _provider_cache
    _provider_cache = {
        p["provider_type"]: {
            "endpoint_url": p.get("endpoint_url"),
            "api_key": p.get("api_key"),
            "auth_header": p.get("auth_header"),
            "temperature": p.get("temperature"),
            "top_p": p.get("top_p"),
            "extra_params": p.get("extra_params"),
        }
        for p in providers
        if p.get("is_enabled")
    }


def _model_str(model: str | None) -> str:
    return model if model else settings.default_llm_model


def is_local_provider(model: str) -> bool:
    return model.startswith(("ollama/", "ollama_chat/", "llama.cpp/", "vllm/"))


def _extra_kwargs(model_id: str) -> dict:
    """Build the per-call kwargs for litellm based on the admin-configured provider."""
    provider_type = model_id.split("/")[0]
    cfg = _provider_cache.get(provider_type, {})
    kwargs: dict = {}

    if is_local_provider(model_id):
        base_url = cfg.get("endpoint_url") or settings.ollama_base_url
        kwargs["api_base"] = base_url
    else:
        # Cloud providers: an explicit api_key in the DB overrides the env var.
        if cfg.get("api_key"):
            kwargs["api_key"] = cfg["api_key"]

    if cfg.get("auth_header"):
        kwargs["extra_headers"] = {"Authorization": cfg["auth_header"]}
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = cfg["temperature"]
    if cfg.get("top_p") is not None:
        kwargs["top_p"] = cfg["top_p"]
    if cfg.get("extra_params"):
        try:
            extra = json.loads(cfg["extra_params"])
            if isinstance(extra, dict):
                # caller-supplied kwargs from this function win on conflict
                merged = {**extra, **kwargs}
                kwargs = merged
        except json.JSONDecodeError:
            logger.warning("Provider %s has malformed extra_params, ignoring", provider_type)

    return kwargs


def _sanitize_messages(messages: list[dict], session_id: str | None, model_id: str) -> tuple[list[dict], int]:
    """Apply Privacy Gate to message content when routing to cloud providers."""
    if not session_id or is_local_provider(model_id) or not settings.enable_privacy_gate:
        return messages, 0

    from androbugger.privacy.gate import get_gate
    gate = get_gate()
    total_replacements = 0
    sanitized = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            result = gate.sanitize(content, session_id)
            total_replacements += result.placeholder_count
            sanitized.append({**msg, "content": result.text})
        else:
            sanitized.append(msg)
    return sanitized, total_replacements


def _restore_response(text: str, session_id: str | None, model_id: str) -> str:
    if not session_id or is_local_provider(model_id) or not settings.enable_privacy_gate:
        return text
    from androbugger.privacy.gate import get_gate
    return get_gate().restore(text, session_id)


async def complete(
    messages: list[dict],
    model: str | None = None,
    user_id: str | None = None,
    device_serial: str | None = None,
    session_id: str | None = None,
) -> LLMResponse:
    model_id = _model_str(model)
    start = time.monotonic()

    send_messages, pii_count = _sanitize_messages(messages, session_id, model_id)

    if pii_count:
        logger.info("Privacy Gate: %d PII items redacted for cloud call to %s", pii_count, model_id)

    async def _call(mid: str, msgs: list[dict]) -> LLMResponse:
        resp = await litellm.acompletion(
            model=mid,
            messages=msgs,
            max_tokens=settings.llm_max_tokens,
            **_extra_kwargs(mid),
        )
        elapsed = (time.monotonic() - start) * 1000
        content = resp.choices[0].message.content or ""
        content = _restore_response(content, session_id, mid)
        usage = resp.usage or {}
        cost = None
        try:
            if not is_local_provider(mid):
                cost = litellm.completion_cost(completion_response=resp)
        except Exception:
            pass
        return LLMResponse(
            content=content,
            provider=mid.split("/")[0],
            model=mid,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            latency_ms=elapsed,
            cost_usd=cost,
        )

    try:
        return await _call(model_id, send_messages)
    except Exception as exc:
        logger.warning("Primary model %s failed: %s — trying fallback", model_id, exc)
        fallback = settings.fallback_llm_model
        if fallback == model_id:
            raise
        fb_msgs, _ = _sanitize_messages(messages, session_id, fallback)
        return await _call(fallback, fb_msgs)


async def stream(
    messages: list[dict],
    model: str | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    model_id = _model_str(model)
    send_messages, _ = _sanitize_messages(messages, session_id, model_id)

    response = await litellm.acompletion(
        model=model_id,
        messages=send_messages,
        max_tokens=settings.llm_max_tokens,
        stream=True,
        **_extra_kwargs(model_id),
    )

    buffer = ""
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            buffer += delta
            yield delta

    # After stream ends, restore PII in the complete buffer would require
    # re-sending — instead the chat WS stores the buffer and restores placeholders
    # before persisting to DB. Yielded chunks already contain placeholders for cloud.
