# Androbugger

**LLM-powered diagnostic platform for Android-based Interactive Flat Panels.**

Connect a returned ADVANTouch IFP, press **Diagnose**, and receive an actionable report identifying the root cause — backed by evidence from the device's own logs — in under 5 minutes.

## Quick Start (Docker)

```bash
git clone https://github.com/brateedinoo/androbugger.git
cd androbugger
cp .env.example .env   # edit SECRET_KEY at minimum
docker compose up -d

# Pull the default local model (one-time, ~8GB)
docker compose exec ollama ollama pull qwen3:14b
docker compose exec ollama ollama pull nomic-embed-text
```

Open **http://localhost** and log in with `admin` / `admin` (you will be prompted to change the password).

## Development Setup

### Backend

```bash
cd backend
uv sync --dev
uv run uvicorn androbugger.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
uv run pytest -v
```

## Architecture

```
Browser (Vue 3 SPA)
  │  REST + WebSocket
  ▼
FastAPI Backend
  ├── Device Layer    (adbutils — USB + wireless ADB)
  ├── Parser Layer    (bugreport, logcat, ANR, tombstone, dumpsys, dmesg)
  ├── LLM Layer       (LiteLLM → Ollama local / cloud fallback)
  ├── Knowledge Layer (ChromaDB + tantivy hybrid search) [Phase 2]
  ├── Privacy Gate    (Presidio PII redaction)            [Phase 2]
  └── Plugin System   (directory-watched, 3-stage validated) [Phase 2]
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Foundation   | 🚧 In progress | ADB, parsers, LLM, minimal UI |
| 2 — Intelligence | ⏳ Planned     | Privacy gate, knowledge base, chat, plugins |
| 3 — Scale        | ⏳ Planned     | Multi-user RBAC, batch diagnostics, export |
| 4 — Evolution    | ⏳ Planned     | Hardware diagnostics, MCP server, fine-tuning |

## Default Credentials

| User  | Password | Role  |
|-------|----------|-------|
| admin | admin    | admin |

Change on first login. Admin account forces password change.

## License

Apache 2.0 — see [LICENSE](LICENSE).
