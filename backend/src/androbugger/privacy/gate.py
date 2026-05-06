"""Mandatory PII sanitisation gate for cloud-bound LLM calls."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from androbugger.privacy.mapper import PlaceholderMapper, get_mapper
from androbugger.privacy.recognizers import all_recognizers

logger = logging.getLogger(__name__)

_LOCAL_PREFIXES = ("ollama/", "ollama_chat/", "llama.cpp/", "vllm/")


def is_cloud_provider(model: str) -> bool:
    return not any(model.startswith(p) for p in _LOCAL_PREFIXES)


@dataclass
class SanitizedResult:
    text: str
    placeholder_count: int


class PrivacyGate:
    def __init__(self, extra_asset_patterns: list[str] | None = None):
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        for rec in all_recognizers(extra_asset_patterns):
            registry.add_recognizer(rec)

        self._analyzer = AnalyzerEngine(registry=registry)
        self._anonymizer = AnonymizerEngine()
        self._mapper: PlaceholderMapper = get_mapper()

    def sanitize(self, text: str, session_id: str) -> SanitizedResult:
        """Detect and replace PII with stable placeholders. Returns sanitised text."""
        try:
            results = self._analyzer.analyze(text=text, language="en")
        except Exception as exc:
            logger.warning("Presidio analysis failed: %s", exc)
            return SanitizedResult(text=text, placeholder_count=0)

        if not results:
            return SanitizedResult(text=text, placeholder_count=0)

        # Build operator map: each entity type gets a unique numbered placeholder
        operators: dict[str, OperatorConfig] = {}
        seen: dict[str, str] = {}  # original_value → placeholder

        for result in results:
            original = text[result.start:result.end]
            if original in seen:
                placeholder = seen[original]
            else:
                placeholder = self._mapper.next_placeholder(session_id, result.entity_type)
                self._mapper.add_mapping(session_id, placeholder, original)
                seen[original] = placeholder

            operators[result.entity_type] = OperatorConfig("replace", {"new_value": placeholder})

        try:
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators,
            )
            return SanitizedResult(text=anonymized.text, placeholder_count=len(seen))
        except Exception as exc:
            logger.warning("Presidio anonymization failed: %s", exc)
            return SanitizedResult(text=text, placeholder_count=0)

    def restore(self, text: str, session_id: str) -> str:
        """Replace placeholders in LLM response with original values."""
        return self._mapper.restore_all(session_id, text)

    def destroy_session(self, session_id: str) -> None:
        self._mapper.destroy_session(session_id)


# Module-level singleton, initialised lazily
_gate: PrivacyGate | None = None


def get_gate() -> PrivacyGate:
    global _gate
    if _gate is None:
        _gate = PrivacyGate()
    return _gate
