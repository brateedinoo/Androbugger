"""In-memory placeholder ↔ original mapping, scoped per diagnostic session."""
import threading
from collections import defaultdict


class PlaceholderMapper:
    """Thread-safe per-session mapping. Never persisted to disk."""

    def __init__(self):
        self._lock = threading.Lock()
        # session_id → {placeholder → original}
        self._sessions: dict[str, dict[str, str]] = defaultdict(dict)
        # session_id → {entity_type → counter}
        self._counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def next_placeholder(self, session_id: str, entity_type: str) -> str:
        with self._lock:
            self._counters[session_id][entity_type] += 1
            n = self._counters[session_id][entity_type]
            return f"[{entity_type}_{n}]"

    def add_mapping(self, session_id: str, placeholder: str, original: str) -> None:
        with self._lock:
            self._sessions[session_id][placeholder] = original

    def get_original(self, session_id: str, placeholder: str) -> str | None:
        with self._lock:
            return self._sessions[session_id].get(placeholder)

    def restore_all(self, session_id: str, text: str) -> str:
        with self._lock:
            mappings = dict(self._sessions.get(session_id, {}))
        for placeholder, original in mappings.items():
            text = text.replace(placeholder, original)
        return text

    def destroy_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._counters.pop(session_id, None)


# Module-level singleton
_mapper = PlaceholderMapper()


def get_mapper() -> PlaceholderMapper:
    return _mapper
