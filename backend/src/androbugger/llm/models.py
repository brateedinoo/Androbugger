from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float | None = None


@dataclass
class VerifiedResponse:
    text: str
    verified_citations: list[dict] = field(default_factory=list)
    unverified_citations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
