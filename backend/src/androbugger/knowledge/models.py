from dataclasses import dataclass, field


@dataclass
class KnowledgeEntry:
    id: str
    namespace: str  # vendor_docs | past_diagnoses | aosp_reference
    title: str
    source: str | None = None
    device_model: str | None = None
    firmware_version: str | None = None
    content_hash: str = ""
    indexed_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    entry_id: str
    title: str
    content_snippet: str
    score: float
    namespace: str
    metadata: dict = field(default_factory=dict)
