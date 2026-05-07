from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANDROBUGGER_", env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Storage
    data_dir: Path = Path("/data/androbugger")
    bugreport_dir: Path = Path("/data/androbugger/bugreports")
    parsed_dir: Path = Path("/data/androbugger/parsed")
    db_path: Path = Path("/data/androbugger/androbugger.db")
    plugin_dir: Path = Path("/app/plugins")
    chroma_path: Path = Path("/data/androbugger/chroma")
    tantivy_path: Path = Path("/data/androbugger/tantivy")

    # LLM
    default_llm_model: str = "ollama/qwen3:14b"
    fallback_llm_model: str = "ollama/qwen3:8b"
    ollama_base_url: str = "http://ollama:11434"
    embedding_model: str = "nomic-embed-text"
    llm_max_tokens: int = 4096

    # Auth
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_hours: int = 8
    refresh_token_expire_hours: int = 24

    # Redis (arq)
    redis_url: str = "redis://redis:6379"

    # Privacy gate
    enable_privacy_gate: bool = True

    # ADB
    adb_device_poll_interval: float = 5.0

    # Audit
    audit_retention_days: int = 90

    # MCP
    mcp_api_key: str = ""

    # SMTP (leave smtp_host empty to disable email)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "androbugger@localhost"

    # Webhooks
    webhook_retry_attempts: int = 3

    # Diagnostic templates
    diagnostic_templates: dict = {
        "default": {"name": "Standard Diagnostic", "focus_areas": []},
        "performance": {"name": "Performance Focus", "focus_areas": ["gfxinfo", "meminfo", "thermal"]},
        "crash": {"name": "Crash Investigation", "focus_areas": ["tombstones", "anr", "logcat"]},
        "network": {"name": "Network Diagnostic", "focus_areas": ["connectivity", "wifi", "bluetooth"]},
    }


settings = Settings()
