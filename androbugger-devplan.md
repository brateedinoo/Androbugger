# Androbugger — Development Plan

**Version 0.1 — May 2026**
**Audience:** LLM coding agents (Claude) and project lead
**Companion document:** Androbugger Whitepaper v0.1

---

## 1. Overview

This document is the implementation specification for Androbugger, an open-source, LLM-powered diagnostic platform for Android-based ADVANTouch Interactive Flat Panels. It is written for two audiences: the project lead (human) and LLM coding agents (primarily Claude) who will implement the system.

Every section is written to be actionable. Library choices include exact package names and minimum versions. Project structure uses explicit file paths. API contracts are defined with request/response shapes. Acceptance criteria are binary — a task is done or it is not. When a coding agent reads a phase section, it should be able to implement the described tasks without asking clarifying questions.

The companion Androbugger Whitepaper (v0.1) describes the vision, architecture rationale, and competitive context. This document describes what to build, with what, in what order, and how to verify it works.

### Constraints

- **Target OS:** Linux (Ubuntu 22.04+ / Debian 12+)
- **Deployment:** Local network only, self-hosted, no external cloud dependency for core functionality
- **Users:** Support technicians, QA engineers, software developers, display repair workshop staff
- **Devices:** ADVANTouch Interactive Flat Panels running Android, connected via USB or wireless ADB (TCP/IP)
- **License:** Open-source (see Section 11)
- **Repository:** GitHub monorepo

## 2. Tech Stack

### Backend

| Component | Package | Min Version | Purpose |
|---|---|---|---|
| Language | Python | 3.11 | All backend logic, ADB communication, LLM orchestration, parsing |
| Package manager | uv | 0.7+ | Dependency management, virtual environments, script running |
| Web framework | FastAPI | 0.115+ | REST + WebSocket API serving the frontend |
| ASGI server | uvicorn | 0.34+ | Production ASGI server for FastAPI |
| ADB client | adbutils | 2.12+ | Programmatic ADB communication (device discovery, shell, bugreport pull, file sync) |
| LLM router | litellm | 1.60+ | Provider-agnostic LLM API (Ollama, OpenAI, Anthropic, Gemini, vLLM, llama.cpp) |
| PII redaction | presidio-analyzer + presidio-anonymizer | 2.2+ | Detect and redact PII before cloud LLM calls |
| Vector database | chromadb | 1.0+ | Embedding storage and semantic search for knowledge base |
| Lexical search | tantivy-py | 0.22+ | BM25 keyword search for exact-match log queries (PIDs, tags, error codes) |
| Embeddings (local) | sentence-transformers | 3.4+ | Local embedding generation using nomic-embed-text or bge-m3 |
| Database | SQLite (aiosqlite) | 0.20+ | Diagnostic history, user accounts, audit log, plugin registry |
| Task queue | arq | 0.26+ | Background jobs (bugreport parsing, embedding generation, batch diagnostics) |
| WebSocket | fastapi + websockets | — | Live logcat streaming, real-time device status updates |
| Screen mirror | scrcpy (system binary) | 2.7+ | Subprocess-managed screen mirroring, streamed to frontend via WebSocket |
| Job broker | redis | 7.0+ | Required by arq for background job queuing |
| Filesystem watcher | watchdog | 5.0+ | Monitor plugin directory for new/modified plugins |
| Password hashing | argon2-cffi | 23.1+ | Argon2id password hashing for user authentication |
| PDF generation | weasyprint | 62.0+ | HTML-to-PDF conversion for diagnostic report export |
| PDF reading | pymupdf | 1.24+ | Read PDF vendor documentation for knowledge base indexing |

### Frontend

| Component | Package | Min Version | Purpose |
|---|---|---|---|
| Framework | Vue 3 | 3.5+ | Reactive UI with Composition API |
| Build tool | Vite | 6.0+ | Fast dev server and production bundler |
| State management | Pinia | 2.3+ | Centralized state for device list, diagnostic sessions, user auth |
| UI components | PrimeVue | 4.3+ | Pre-built accessible component library (tables, panels, dialogs, forms) |
| HTTP client | ofetch | 1.4+ | Lightweight fetch wrapper for API calls |
| WebSocket client | Native WebSocket API | — | Live logcat stream, device status, screen mirror frames |
| CSS | Tailwind CSS | 4.0+ | Utility-first styling |
| Router | vue-router | 4.5+ | SPA routing |
| Icons | Lucide Vue | 0.460+ | Icon set |
| Markdown rendering | markdown-it | 14.0+ | Render LLM responses and diagnostic reports |
| Terminal emulator | xterm.js | 5.5+ | In-browser ADB shell for developer role |

### Infrastructure

| Component | Tool | Purpose |
|---|---|---|
| Local LLM runtime | Ollama | Serve local models (Qwen3 8B/14B, Llama 3.1 8B, Phi-4 Mini) |
| Containerization | Docker + Docker Compose | Package backend, frontend, Ollama, LiteLLM proxy, and Redis as a single deployable stack |
| Reverse proxy | Caddy | TLS termination, static file serving, WebSocket proxying on local network |
| Version control | Git + GitHub | Monorepo hosting, issues, CI/CD |
| CI/CD | GitHub Actions | Linting, testing, building, container image publishing |

### Default Local Models

| Model | Parameter Count | Quantization | Use Case | Context Window |
|---|---|---|---|---|
| Qwen3 14B | 14B | Q4_K_M | Primary diagnostic model (log analysis, root cause) | 32K native, 131K with YaRN |
| Qwen3 8B | 8B | Q4_K_M | Fallback / lower-resource machines | 32K native, 131K with YaRN |
| Llama 3.1 8B | 8B | Q4_K_M | Alternative if Qwen3 underperforms on specific tasks | 128K |
| nomic-embed-text | 137M | FP16 | Local embedding generation for knowledge base | 8K |

### Project Structure

```
androbugger/
├── docker-compose.yml
├── Caddyfile
├── README.md
├── LICENSE
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── backend/
│   ├── pyproject.toml          # uv project config
│   ├── uv.lock
│   ├── src/
│   │   └── androbugger/
│   │       ├── __init__.py
│   │       ├── main.py             # FastAPI app entry point
│   │       ├── config.py           # Settings (pydantic-settings)
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── devices.py      # Device list, connect, disconnect endpoints
│   │       │   ├── diagnostics.py  # Diagnose, history, export endpoints
│   │       │   ├── chat.py         # AI chat WebSocket endpoint
│   │       │   ├── logcat.py       # Live logcat WebSocket endpoint
│   │       │   ├── commands.py     # Natural language ADB + direct ADB shell
│   │       │   ├── plugins.py      # Plugin management endpoints
│   │       │   ├── auth.py         # User auth + RBAC endpoints
│   │       │   └── admin.py        # LLM config, budgets, audit log
│   │       ├── device/
│   │       │   ├── __init__.py
│   │       │   ├── manager.py      # Device discovery, connection pool, transport management
│   │       │   ├── adb.py          # adbutils wrapper with permission tiers
│   │       │   ├── scrcpy.py       # scrcpy subprocess management
│   │       │   └── models.py       # Device dataclasses
│   │       ├── parser/
│   │       │   ├── __init__.py
│   │       │   ├── bugreport.py    # Zip splitter, section router
│   │       │   ├── logcat.py       # Logcat line parser (threadtime format)
│   │       │   ├── anr.py          # ANR trace parser
│   │       │   ├── tombstone.py    # Native crash tombstone parser
│   │       │   ├── dumpsys.py      # Dumpsys section parsers (meminfo, battery, activity, gfxinfo)
│   │       │   ├── dmesg.py        # Kernel log parser
│   │       │   ├── summary.py      # Deterministic diagnostic summary generator
│   │       │   └── models.py       # Parsed data dataclasses
│   │       ├── knowledge/
│   │       │   ├── __init__.py
│   │       │   ├── store.py        # Chroma + tantivy hybrid search interface
│   │       │   ├── embeddings.py   # Embedding generation (local via sentence-transformers)
│   │       │   ├── indexer.py      # Index past diagnoses, vendor docs, AOSP reference
│   │       │   └── models.py       # Knowledge entry dataclasses
│   │       ├── privacy/
│   │       │   ├── __init__.py
│   │       │   ├── gate.py         # Presidio-based PII detection + redaction
│   │       │   ├── recognizers.py  # Custom recognizers (asset tags, MAC, IMEI, SSID, AD usernames)
│   │       │   └── mapper.py       # Placeholder ↔ original session mapping (in-memory only)
│   │       ├── llm/
│   │       │   ├── __init__.py
│   │       │   ├── router.py       # LiteLLM wrapper, provider routing, fallback logic
│   │       │   ├── prompts.py      # Prompt templates for diagnostic analysis
│   │       │   ├── verifier.py     # Post-processing: verify LLM-cited log lines exist
│   │       │   └── models.py       # LLM request/response dataclasses
│   │       ├── plugins/
│   │       │   ├── __init__.py
│   │       │   ├── loader.py       # Watch directory, load plugins, manage registry
│   │       │   ├── validator.py    # Schema check, sandbox test, dependency verification
│   │       │   ├── sandbox.py      # Runtime permission enforcement
│   │       │   └── models.py       # Plugin manifest dataclasses
│   │       ├── auth/
│   │       │   ├── __init__.py
│   │       │   ├── users.py        # User CRUD, password hashing
│   │       │   ├── roles.py        # Role definitions and permission checks
│   │       │   └── middleware.py   # FastAPI auth middleware
│   │       ├── mcp/
│   │       │   ├── __init__.py
│   │       │   └── server.py       # MCP server exposing diagnostic tools (Phase 4)
│   │       └── db/
│   │           ├── __init__.py
│   │           ├── database.py     # SQLite connection management (aiosqlite)
│   │           ├── migrations.py   # Schema migrations
│   │           └── models.py       # SQLAlchemy/raw SQL table definitions
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── fixtures/               # Sample bugreports, logcat files, ANR traces for testing
│   │   │   ├── bugreport_sample.zip
│   │   │   ├── logcat_crash.txt
│   │   │   ├── anr_trace.txt
│   │   │   └── tombstone_sample.txt
│   │   ├── test_parser/
│   │   ├── test_device/
│   │   ├── test_knowledge/
│   │   ├── test_privacy/
│   │   ├── test_llm/
│   │   └── test_plugins/
│   └── plugins/                    # Plugin drop directory (watched at runtime)
│       └── _example_plugin/
│           ├── manifest.json
│           └── plugin.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router/
│       │   └── index.ts
│       ├── stores/
│       │   ├── devices.ts          # Device list state
│       │   ├── diagnostics.ts      # Active diagnostic session state
│       │   ├── chat.ts             # AI chat state
│       │   ├── auth.ts             # User session state
│       │   └── plugins.ts          # Plugin registry state
│       ├── composables/
│       │   ├── useWebSocket.ts     # WebSocket connection manager
│       │   ├── useLogcat.ts        # Live logcat stream composable
│       │   └── useScrcpy.ts        # Screen mirror stream composable
│       ├── views/
│       │   ├── DashboardView.vue   # Device list + health overview
│       │   ├── DiagnosticView.vue  # Active diagnosis: report + chat + logcat
│       │   ├── HistoryView.vue     # Past diagnostic sessions
│       │   ├── PluginsView.vue     # Plugin management (dev/admin role)
│       │   ├── AdminView.vue       # LLM config, users, budgets, audit log
│       │   └── LoginView.vue
│       ├── components/
│       │   ├── DeviceCard.vue
│       │   ├── DiagnosticReport.vue
│       │   ├── ChatPanel.vue
│       │   ├── LogcatViewer.vue
│       │   ├── ScreenMirror.vue
│       │   ├── CommandInput.vue
│       │   ├── FirmwareCompare.vue
│       │   └── ExportDialog.vue
│       └── types/
│           └── index.ts            # TypeScript interfaces matching backend models
└── docs/
    ├── whitepaper.md
    ├── development-plan.md
    ├── plugin-developer-guide.md
    └── api-reference.md
```

## 3. System Architecture (Technical)

### Component Communication

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 SPA)                                                │
│  ├── HTTP REST  →  FastAPI endpoints (devices, diagnostics, auth)   │
│  ├── WebSocket  →  /ws/logcat/{device_serial}  (live log stream)    │
│  ├── WebSocket  →  /ws/chat/{session_id}       (AI chat)            │
│  ├── WebSocket  →  /ws/scrcpy/{device_serial}  (screen mirror)     │
│  └── WebSocket  →  /ws/devices                 (device status feed) │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Caddy reverse proxy (TLS, static files)
┌──────────────────────────▼──────────────────────────────────────────┐
│  FastAPI Backend (uvicorn, single process, async)                    │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ Device Mgr   │  │ Parser      │  │ Knowledge    │  │ Auth/RBAC │ │
│  │              │  │             │  │              │  │           │ │
│  │ adbutils     │  │ bugreport   │  │ chromadb     │  │ SQLite    │ │
│  │ scrcpy proc  │  │ logcat      │  │ tantivy-py   │  │ JWT       │ │
│  │ perm tiers   │  │ anr         │  │ sentence-tx  │  │ roles     │ │
│  │              │  │ tombstone   │  │              │  │           │ │
│  │              │  │ dumpsys     │  │              │  │           │ │
│  │              │  │ dmesg       │  │              │  │           │ │
│  │              │  │ summary     │  │              │  │           │ │
│  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘  └───────────┘ │
│         │                 │                │                         │
│  ┌──────▼─────────────────▼────────────────▼───────────────────────┐ │
│  │                    LLM Orchestration                             │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │ │
│  │  │ Privacy Gate  │  │ LLM Router   │  │ Verifier               │ │ │
│  │  │ (Presidio)    │→│ (LiteLLM)    │→│ (cite check, halluc.)  │ │ │
│  │  └──────────────┘  └──────┬───────┘  └────────────────────────┘ │ │
│  └───────────────────────────┼─────────────────────────────────────┘ │
│                              │                                       │
│  ┌───────────────────────────▼─────────────────────────────────────┐ │
│  │                    Plugin Runtime                                │ │
│  │  loader → validator → sandbox → plugin registry                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Background Workers (arq)                                       │ │
│  │  - bugreport parse jobs                                          │ │
│  │  - embedding generation                                          │ │
│  │  - batch diagnostics                                             │ │
│  │  - plugin validation                                             │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐           ┌─────────────────────┐
│  Ollama          │           │  Cloud LLM APIs      │
│  (localhost:11434)│           │  (OpenAI, Anthropic,  │
│  qwen3:14b       │           │   Gemini — opt-in)    │
│  nomic-embed-text│           │                       │
└─────────────────┘           └─────────────────────┘
```

### Data Flow: One-Click Diagnosis

This is the primary user workflow. When a technician presses "Diagnose" on a connected panel, the following sequence executes:

```
1. Frontend sends POST /api/diagnostics/start { device_serial }
2. Backend validates user role (technician+) and device connection status
3. Device Manager executes: adb -s {serial} bugreport /tmp/{session_id}.zip
4. Background worker picks up the parse job:
   a. Unzip bugreport archive
   b. Identify bugreport-*.txt, FS/data/anr/*, FS/data/tombstones/*
   c. Run section splitter (regex on ------ SECTION_NAME ------ headers)
   d. For each section, dispatch to typed parser:
      - logcat → list of {ts, pid, tid, level, tag, msg}
      - ANR → {process, pid, reason, main_thread_stack[], other_threads[]}
      - tombstone → {process, signal, registers, backtrace[], memory_map[]}
      - dumpsys/meminfo → {total_ram, free_ram, per_process_pss[]}
      - dumpsys/batterystats → {screen_on_time, wake_locks[], top_consumers[]}
      - dumpsys/activity → {running_activities[], recent_tasks[], crashed_processes[]}
      - dmesg → {thermal_events[], oom_kills[], selinux_denials[]}
   e. Generate deterministic diagnostic summary:
      - Top 10 errors by frequency and tag
      - All ANR events in the last 24 hours
      - All tombstones
      - OOM events and low-memory entries
      - Thermal throttle events
      - Crash loops (same process crashing 3+ times in 1 hour)
      - Boot anomalies
5. Knowledge Layer queries:
   a. Embed the diagnostic summary
   b. Run hybrid search (BM25 + vector) filtered by device model and firmware version
   c. Retrieve top 5 matching past diagnoses and top 3 matching vendor KB entries
6. Privacy Gate: if LLM provider is cloud, run Presidio on all text to be sent; else skip
7. LLM prompt assembly:
   - System prompt: structured diagnostic analysis template
   - Context: deterministic summary + retrieved knowledge entries + key parsed sections
   - Instruction: identify root cause, cite log evidence, declare confidence, recommend fix
8. LLM call via LiteLLM router → response
9. Verifier: check every cited log line number / process name / error code against parsed data
   - Verified citations: kept
   - Unverifiable citations: flagged with warning
10. Store diagnostic session in SQLite:
    - device_serial, firmware_version, session_id, timestamp
    - raw bugreport path, parsed data (JSON), deterministic summary
    - LLM prompt, LLM response, provider/model used, token count
    - verification results
    - status: open (pending human confirmation of root cause)
11. Return structured report to frontend via REST response
12. Frontend renders DiagnosticReport.vue
```

### Data Flow: Natural Language ADB

```
1. User types "check memory usage" in CommandInput.vue
2. Frontend sends POST /api/commands/natural { device_serial, query }
3. LLM translates query → ADB command(s):
   - Prompt: "Translate the following user intent into one or more ADB shell commands.
     User intent: {query}
     Respond with JSON: { commands: [{ cmd: string, destructive: boolean }] }"
4. Permission tier check for each command:
   - Read-only (logcat, dumpsys, getprop, ps, top, df): execute immediately
   - State-changing (pm clear, am force-stop, svc, settings put): hold for confirmation
   - Destructive (reboot, wipe, factory reset): hold for confirmation + require role ≥ developer
5. If confirmation needed: return commands to frontend with confirmation prompt
   - User confirms → Frontend sends POST /api/commands/execute { session_id, confirmed: true }
6. Device Manager executes command(s) via adbutils
7. Audit log entry: { user, device_serial, command, output, timestamp, confirmed_by }
8. LLM interprets results in readable format
9. Return formatted results to frontend
```

### Data Flow: Live Logcat with "Explain This"

```
1. Frontend opens WebSocket /ws/logcat/{device_serial}
2. Backend starts: adb -s {serial} logcat -v threadtime (via adbutils streaming shell)
3. Each line is parsed into { ts, pid, tid, level, tag, msg } and sent to frontend
4. Frontend renders in LogcatViewer.vue with filter controls
5. User selects one or more log lines, clicks "Explain this"
6. Frontend sends POST /api/chat/explain { device_serial, selected_lines[] }
7. LLM prompt: "Explain the following Android logcat entries. State whether they indicate
   a problem, and if so, what the likely cause is. Cite specific entries by line number."
8. Response rendered inline below the selected lines
```

### Data Flow: AI Chat

```
1. Frontend opens WebSocket /ws/chat/{session_id}
2. Session context is loaded: current diagnostic report, parsed data, device info
3. User sends a message (e.g., "Is this crash related to the one from yesterday?")
4. Backend assembles prompt:
   - System: diagnostic assistant context
   - History: previous messages in this chat session
   - Context: current diagnostic summary + relevant parsed sections
   - If question references past cases: query Knowledge Layer
5. Privacy Gate (if cloud provider)
6. LLM call → streamed response via WebSocket
7. Verifier runs on completed response
8. Chat message pair stored in SQLite (linked to diagnostic session)
```

### Database Schema (SQLite)

```sql
-- Users and authentication
CREATE TABLE users (
    id TEXT PRIMARY KEY,            -- UUID
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('technician', 'qa_engineer', 'developer', 'admin')),
    force_password_change BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL,
    last_login TEXT
);

-- Connected devices (ephemeral, rebuilt on startup)
CREATE TABLE devices (
    serial TEXT PRIMARY KEY,
    model TEXT,
    firmware_version TEXT,
    connection_type TEXT CHECK (connection_type IN ('usb', 'tcp')),
    ip_address TEXT,                -- NULL for USB connections
    connected_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

-- Diagnostic sessions
CREATE TABLE diagnostic_sessions (
    id TEXT PRIMARY KEY,            -- UUID
    device_serial TEXT NOT NULL,
    device_model TEXT,
    firmware_version TEXT,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'resolved', 'failed')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    bugreport_path TEXT,            -- Path to stored bugreport zip
    parsed_data_path TEXT,          -- Path to parsed JSON
    deterministic_summary TEXT,     -- JSON blob
    llm_report TEXT,                -- LLM-generated diagnostic report (markdown)
    llm_provider TEXT,              -- e.g., 'ollama/qwen3:14b' or 'anthropic/claude-sonnet-4-5'
    llm_token_count INTEGER,
    llm_cost_estimate REAL,         -- USD, NULL for local models
    root_cause TEXT,                -- Human-confirmed root cause (set on resolve)
    applied_fix TEXT,               -- Human-confirmed fix (set on resolve)
    resolution_notes TEXT
);

-- Chat messages within diagnostic sessions
CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES diagnostic_sessions(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    llm_provider TEXT,
    token_count INTEGER
);

-- Audit log (append-only)
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,           -- e.g., 'adb_command', 'llm_call', 'plugin_load', 'login', 'diagnose_start'
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    device_serial TEXT,
    detail TEXT,                    -- JSON blob with action-specific data
    ip_address TEXT
);

-- Plugin registry
CREATE TABLE plugins (
    id TEXT PRIMARY KEY,            -- Plugin folder name
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    author TEXT,
    description TEXT,
    manifest_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'quarantined', 'validating')),
    loaded_at TEXT,
    validation_result TEXT,         -- JSON blob with validation details
    permissions TEXT                -- JSON array of declared permissions
);

-- Knowledge base entries (metadata — vectors stored in Chroma)
CREATE TABLE knowledge_entries (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL CHECK (namespace IN ('vendor_docs', 'past_diagnoses', 'aosp_reference')),
    title TEXT NOT NULL,
    source TEXT,                    -- File path, URL, or diagnostic session ID
    device_model TEXT,              -- NULL = applies to all models
    firmware_version TEXT,          -- NULL = applies to all versions
    content_hash TEXT NOT NULL,     -- SHA256 of content, for dedup
    indexed_at TEXT NOT NULL,
    metadata TEXT                   -- JSON blob with additional filters
);

-- LLM provider configuration
CREATE TABLE llm_providers (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,    -- 'ollama', 'openai', 'anthropic', 'gemini', 'vllm', 'custom'
    model_name TEXT NOT NULL,
    endpoint_url TEXT,              -- NULL for cloud providers with known endpoints
    is_local BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,    -- Higher = tried first in fallback chain
    max_tokens INTEGER DEFAULT 4096,
    budget_limit_usd REAL,         -- NULL = unlimited (local models)
    budget_spent_usd REAL DEFAULT 0.0,
    budget_reset_interval TEXT      -- 'daily', 'weekly', 'monthly', NULL
);

-- Batch diagnostic runs (Phase 3)
CREATE TABLE batch_diagnostics (
    id TEXT PRIMARY KEY,            -- UUID
    user_id TEXT NOT NULL REFERENCES users(id),
    device_serials TEXT NOT NULL,   -- JSON array of serials
    session_ids TEXT NOT NULL,      -- JSON array of created diagnostic session IDs
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    summary TEXT                    -- JSON blob with per-device status and outlier flags
);

-- ADB command permission tiers
CREATE TABLE command_permissions (
    pattern TEXT PRIMARY KEY,       -- Glob pattern, e.g., 'logcat*', 'pm clear*', 'reboot*'
    tier TEXT NOT NULL CHECK (tier IN ('read_only', 'state_changing', 'destructive')),
    min_role TEXT NOT NULL CHECK (min_role IN ('technician', 'qa_engineer', 'developer', 'admin')),
    requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT
);
```

### API Endpoints Summary

```
Authentication:
  POST   /api/auth/login              { username, password } → { token, user }
  POST   /api/auth/logout             → { ok }
  GET    /api/auth/me                 → { user }

Devices:
  GET    /api/devices                 → { devices[] }
  POST   /api/devices/connect         { serial | ip_address } → { device }
  POST   /api/devices/disconnect      { serial } → { ok }
  GET    /api/devices/{serial}/info   → { device_detail }

Diagnostics:
  POST   /api/diagnostics/start       { device_serial } → { session_id }
  GET    /api/diagnostics/{id}        → { session }
  GET    /api/diagnostics/{id}/report → { report_markdown }
  POST   /api/diagnostics/{id}/resolve { root_cause, applied_fix, notes } → { ok }
  GET    /api/diagnostics/history     ?device_serial=&firmware=&status=&from=&to= → { sessions[] }
  GET    /api/diagnostics/search      ?q= → { sessions[] }
  POST   /api/diagnostics/{id}/export { format: 'pdf' | 'markdown' } → { file }

Commands:
  POST   /api/commands/natural        { device_serial, query } → { commands[], needs_confirmation }
  POST   /api/commands/execute        { device_serial, commands[], confirmed } → { results[] }
  POST   /api/commands/raw            { device_serial, command } → { output }  (developer+ only)

Chat:
  WebSocket /ws/chat/{session_id}     Bidirectional: user messages ↔ assistant responses
  POST   /api/chat/explain            { device_serial, selected_lines[] } → { explanation }

Logcat:
  WebSocket /ws/logcat/{serial}       Server → client: parsed logcat lines
  
Screen Mirror:
  WebSocket /ws/scrcpy/{serial}       Server → client: screen frames

Device Status:
  WebSocket /ws/devices               Server → client: connection/disconnection events

Plugins:
  GET    /api/plugins                 → { plugins[] }
  POST   /api/plugins/validate        { plugin_id } → { validation_result }
  POST   /api/plugins/{id}/activate   → { ok }
  POST   /api/plugins/{id}/deactivate → { ok }

Admin:
  GET    /api/admin/providers         → { providers[] }
  PUT    /api/admin/providers/{id}    { config } → { provider }
  GET    /api/admin/audit             ?user=&action=&severity=&from=&to= → { entries[] }
  GET    /api/admin/usage             ?provider=&from=&to= → { usage_stats }
  GET    /api/admin/users             → { users[] }
  POST   /api/admin/users             { username, password, role } → { user }
  PUT    /api/admin/users/{id}        { role } → { user }
  DELETE /api/admin/users/{id}        → { ok }

Firmware Comparison:
  POST   /api/diagnostics/compare     { session_id_a, session_id_b } → { diff_report }
```

## 4. Phase 1: Foundation

### Goal

Deliver a working diagnostic tool that connects to ADVANTouch panels over USB and wireless ADB, captures and parses bugreports, generates a deterministic diagnostic summary, and provides basic LLM-powered interpretation via a minimal web UI. At the end of Phase 1, a technician can connect a panel, press "Diagnose," and receive a useful report — replacing days of manual log reading with minutes of automated analysis.

### Task Breakdown

#### 4.1 Project Scaffolding

```
Tasks:
  - Initialize GitHub monorepo with the project structure from Section 2
  - Set up backend Python project with uv (pyproject.toml, uv.lock)
  - Set up frontend Vue 3 project with Vite, Tailwind CSS, PrimeVue
  - Create docker-compose.yml with services: backend, frontend, ollama
  - Create Caddyfile for reverse proxy (frontend static, /api → backend, /ws → backend)
  - Add .github/workflows/ci.yml: lint (ruff), type check (mypy), test (pytest), frontend build
  - Add README.md with setup instructions for Linux (Ubuntu 22.04+)

Acceptance criteria:
  - `docker compose up` starts all services and serves the Vue app at https://localhost
  - `uv run pytest` passes with zero tests (framework runs)
  - `cd frontend && npm run build` produces a dist/ folder
  - CI workflow runs on push and passes
```

#### 4.2 Device Layer

```
Tasks:
  - Implement DeviceManager class in backend/src/androbugger/device/manager.py:
    - discover_usb() → list of device serials via adbutils
    - connect_tcp(ip, port=5555) → connect to wireless ADB device
    - disconnect(serial) → disconnect device
    - list_connected() → list of DeviceInfo dataclasses
    - get_device(serial) → single DeviceInfo or raise NotFound
    - Background task: poll connected devices every 5 seconds, emit status via WebSocket
  - Implement ADB wrapper in backend/src/androbugger/device/adb.py:
    - shell(serial, command: list[str]) → stdout string
    - shell_stream(serial, command: list[str]) → async generator of lines
    - pull_bugreport(serial) → path to saved zip file
    - screencap(serial) → PNG bytes
    - getprop(serial) → dict of all device properties
    - install(serial, apk_path) → result (confirmation required)
    - Permission tier decorator: @permission_tier('read_only' | 'state_changing' | 'destructive')
    - All commands logged to audit log: user, serial, command, output, timestamp
  - Implement DeviceInfo dataclass in backend/src/androbugger/device/models.py:
    - serial, model, firmware_version, connection_type, ip_address, android_version,
      build_fingerprint, connected_at, last_seen
  - Implement REST endpoints in backend/src/androbugger/api/devices.py:
    - GET /api/devices
    - POST /api/devices/connect
    - POST /api/devices/disconnect
    - GET /api/devices/{serial}/info
  - Implement WebSocket /ws/devices for real-time connection/disconnection events

Acceptance criteria:
  - Connect an Android device via USB, GET /api/devices returns its serial, model, firmware
  - Connect an Android device via TCP (POST /api/devices/connect {ip}), same result
  - shell("logcat", "-d", "-t", "10") returns 10 logcat lines as parsed text
  - pull_bugreport() downloads a zip file to the configured storage path
  - Disconnecting a USB cable triggers a disconnect event on /ws/devices within 10 seconds
  - Every ADB command execution creates an audit_log row
```

#### 4.3 Parser Layer

```
Tasks:
  - Implement bugreport zip splitter in backend/src/androbugger/parser/bugreport.py:
    - unzip(zip_path) → extracted directory path
    - identify_main_file(extracted_path) → path to bugreport-*.txt
    - identify_anr_files(extracted_path) → list of paths in FS/data/anr/
    - identify_tombstone_files(extracted_path) → list of paths in FS/data/tombstones/
    - split_sections(main_file_path) → dict[section_name, section_text]
      Section boundary regex: r'^------\s+(.+?)\s+------$'
  - Implement logcat parser in backend/src/androbugger/parser/logcat.py:
    - parse_line(line: str) → LogcatEntry { ts, pid, tid, level, tag, msg } or None
      Format: threadtime — "MM-DD HH:MM:SS.mmm  PID  TID LEVEL TAG : MSG"
    - parse_buffer(text: str) → list[LogcatEntry]
    - filter_by_level(entries, min_level: str) → list[LogcatEntry]
    - group_by_tag(entries) → dict[tag, list[LogcatEntry]]
    - error_frequency(entries) → list[{tag, count, sample_msg}] sorted desc
  - Implement ANR parser in backend/src/androbugger/parser/anr.py:
    - parse_anr_file(text: str) → ANRTrace { process, pid, reason, timestamp,
      main_thread_stack: list[str], other_threads: list[ThreadDump] }
    - ThreadDump: { name, state, stack: list[str] }
  - Implement tombstone parser in backend/src/androbugger/parser/tombstone.py:
    - parse_tombstone(text: str) → Tombstone { process, pid, tid, signal, signal_name,
      fault_addr, registers: dict, backtrace: list[FrameInfo], memory_map: list[str],
      open_files: list[str], timestamp }
    - FrameInfo: { frame_num, pc, library, function, offset }
  - Implement dumpsys parsers in backend/src/androbugger/parser/dumpsys.py:
    - parse_meminfo(text: str) → MemInfo { total_ram_kb, free_ram_kb, used_ram_kb,
      per_process: list[{process, pss_kb, rss_kb}] }
    - parse_batterystats(text: str) → BatteryStats { screen_on_time_ms,
      top_consumers: list[{uid, package, drain_pct}], wake_locks: list[{name, count, total_ms}] }
    - parse_activity(text: str) → ActivityInfo { running_activities: list[str],
      recent_tasks: list[str], crashed_processes: list[{process, count, last_crash}] }
    - parse_gfxinfo(text: str) → GfxInfo { janky_frames_pct: float,
      per_activity: list[{activity, total_frames, janky_frames}] }
  - Implement dmesg parser in backend/src/androbugger/parser/dmesg.py:
    - parse_dmesg(text: str) → list[DmesgEntry { timestamp_secs, level, facility, msg }]
    - extract_thermal_events(entries) → list[ThermalEvent { ts, zone, temp_c, action }]
    - extract_oom_kills(entries) → list[OOMKill { ts, process, pid, score_adj, pages_freed }]
    - extract_selinux_denials(entries) → list[SELinuxDenial { ts, scontext, tcontext, tclass, action }]
  - Implement deterministic summary generator in backend/src/androbugger/parser/summary.py:
    - generate_summary(parsed_bugreport: ParsedBugreport) → DiagnosticSummary
    - DiagnosticSummary:
      - top_errors: list[{tag, count, level, sample_msg}]  (top 10 by frequency)
      - anr_events: list[ANRTrace]  (last 24h)
      - tombstones: list[Tombstone]
      - oom_events: list[OOMKill]
      - thermal_events: list[ThermalEvent]
      - crash_loops: list[{process, crash_count, time_window}]  (3+ crashes in 1 hour)
      - selinux_denials: list[SELinuxDenial]
      - device_uptime_seconds: int
      - low_memory_events_count: int
      - severity: 'critical' | 'warning' | 'info'  (based on presence of tombstones/ANRs/OOMs)

Acceptance criteria:
  - Given the sample bugreport zip in tests/fixtures/bugreport_sample.zip:
    - Splitter identifies the main bugreport file, ANR files, and tombstone files
    - Logcat parser extracts ≥95% of lines with correct fields (validate against manual count)
    - ANR parser extracts process, reason, and main thread stack
    - Tombstone parser extracts signal, backtrace with library and function names
    - Dumpsys parsers extract structured data from meminfo, batterystats, activity, gfxinfo
    - Summary generator produces a valid DiagnosticSummary with populated fields
  - All parsers handle malformed input gracefully (return partial results, never crash)
  - Parser tests run without network or device — pure text in, structured data out
  - Full bugreport parse completes in <30 seconds for a 100MB bugreport
```

#### 4.4 Basic LLM Integration

```
Tasks:
  - Implement LLM router in backend/src/androbugger/llm/router.py:
    - complete(messages: list[dict], model: str | None) → LLMResponse
    - stream(messages: list[dict], model: str | None) → async generator of chunks
    - Uses LiteLLM under the hood: litellm.acompletion() / litellm.acompletion() with stream=True
    - Default model: "ollama/qwen3:14b" (from config)
    - Fallback chain: try default → try fallback model → return error with deterministic summary
    - Log every call: user, device, provider, model, prompt tokens, completion tokens, latency_ms
  - Implement prompt templates in backend/src/androbugger/llm/prompts.py:
    - DIAGNOSTIC_SYSTEM_PROMPT: structured diagnostic analysis template that instructs the LLM to:
      - Identify root cause category (memory pressure, process crash, binder deadlock,
        thermal throttle, configuration error, firmware bug, app crash, other)
      - Cite specific log evidence by section and line reference
      - Declare confidence level (low, medium, high)
      - Separate observations from conclusions
      - Recommend specific fix actions
      - Output in a consistent markdown format
    - build_diagnostic_prompt(summary: DiagnosticSummary, parsed_sections: dict) → list[dict]
      Assembles system prompt + summary + relevant parsed sections, respecting token budget
  - Implement citation verifier in backend/src/androbugger/llm/verifier.py:
    - verify_citations(llm_response: str, parsed_data: ParsedBugreport) → VerifiedResponse
    - VerifiedResponse: { text: str, verified_citations: list, unverified_citations: list,
      warnings: list[str] }
    - Checks: log line references exist, process names exist in parsed data,
      error codes appear in the source
  - Configure Ollama in docker-compose.yml:
    - Pull qwen3:14b and qwen3:8b on first startup
    - Expose on localhost:11434
    - GPU passthrough if available (nvidia runtime)
  - Implement diagnostic endpoint in backend/src/androbugger/api/diagnostics.py:
    - POST /api/diagnostics/start → triggers bugreport pull, parse, LLM analysis
    - GET /api/diagnostics/{id} → returns session with report
    - GET /api/diagnostics/{id}/report → returns rendered markdown report

Acceptance criteria:
  - POST /api/diagnostics/start with a connected device:
    - Returns session_id within 2 seconds
    - Bugreport is captured, parsed, and LLM analysis completes within 5 minutes
    - GET /api/diagnostics/{id} returns status 'completed' with a non-empty llm_report
  - The LLM report contains: root cause section, evidence section with log references,
    confidence declaration, recommended actions
  - Citation verifier catches at least 1 fabricated reference when tested with a
    deliberately hallucinated response
  - If Ollama is down, POST /api/diagnostics/start still returns a valid session with
    the deterministic summary (llm_report is null, deterministic_summary is populated)
  - Every LLM call creates an audit_log row with provider, model, token count
```

#### 4.5 Minimal Web UI

```
Tasks:
  - Implement LoginView.vue:
    - Username + password form
    - Stores JWT in memory (not localStorage — use Pinia store)
    - Redirects to dashboard on success
  - Implement DashboardView.vue:
    - Lists all connected devices as DeviceCard.vue components
    - Each card shows: serial, model, firmware version, connection type, status indicator
    - "Connect Device" button: input field for IP address (wireless) or auto-detect USB
    - Real-time updates via /ws/devices WebSocket
    - "Diagnose" button on each device card → navigates to DiagnosticView
  - Implement DiagnosticView.vue:
    - Shows progress indicator while diagnosis is running
    - Renders DiagnosticReport.vue when complete:
      - Deterministic summary section (always shown)
      - LLM analysis section (shown when available)
      - Evidence citations with visual indicators (verified ✓ / unverified ⚠)
      - Recommended actions list
      - Root cause confidence badge (low/medium/high)
    - "Resolve" button: form to confirm root cause, applied fix, notes → POST /api/diagnostics/{id}/resolve
  - Implement basic routing in router/index.ts:
    - / → LoginView (if not authed) or DashboardView (if authed)
    - /diagnose/:sessionId → DiagnosticView
  - Implement basic auth store in stores/auth.ts:
    - login(username, password), logout(), isAuthenticated, currentUser
  - Implement devices store in stores/devices.ts:
    - devices list, connectDevice(), disconnectDevice(), WebSocket connection management

Acceptance criteria:
  - User can log in, see connected devices, and trigger a diagnosis from the browser
  - Diagnostic report renders with both deterministic summary and LLM analysis
  - Verified and unverified citations are visually distinguished
  - "Resolve" button saves root cause and fix to the database
  - UI is usable on a 1920x1080 screen at default zoom without horizontal scrolling
  - Page load (after login) completes in <2 seconds on localhost
```

#### 4.6 Database and Audit Foundation

```
Tasks:
  - Implement SQLite database setup in backend/src/androbugger/db/database.py:
    - async get_db() → aiosqlite connection
    - init_db() → create all tables from schema (Section 3)
    - Runs on startup via FastAPI lifespan
  - Implement migrations.py:
    - Simple version-tracked migration system (schema_version table)
    - Each migration is a .sql file in backend/src/androbugger/db/migrations/
  - Seed default data:
    - Default admin user (admin/admin, must change on first login)
    - Default command permission tiers (logcat→read_only, dumpsys→read_only,
      getprop→read_only, pm clear→state_changing, reboot→destructive, etc.)
    - Default LLM provider entry (ollama/qwen3:14b, local, default)
  - Implement audit logging in every API endpoint and device command

Acceptance criteria:
  - Fresh `docker compose up` creates the database with all tables and seed data
  - Admin user can log in with default credentials and is prompted to change password
  - After running a full diagnosis, the audit_log table contains entries for:
    device connection, bugreport pull command, LLM call, diagnostic session creation
  - Audit log entries have correct user_id, timestamp, device_serial, and action
```

### Phase 1 Deliverables

```
1. Working Docker Compose stack: backend + frontend + Ollama
2. USB and wireless ADB device connectivity with auto-discovery
3. Full bugreport capture, parsing, and deterministic summary generation
4. LLM-powered diagnostic report with citation verification
5. Minimal web UI: login, device dashboard, diagnostic report, resolve flow
6. Audit logging of all ADB commands and LLM calls
7. CI pipeline: lint, type check, unit tests
```

### Phase 1 Success Criteria

```
- The tool produces a useful diagnostic report for ≥80% of a curated set of
  20 real ADVANTouch bugreports, judged by 2 internal engineers
- Mean time from "Diagnose" button press to rendered report: <5 minutes
- Deterministic summary is always generated, even if LLM is unavailable
- All ADB commands and LLM calls are audit-logged
- Zero unhandled exceptions in backend during a 20-bugreport test run
```

## 5. Phase 2: Intelligence

### Goal

Make the system learn from every resolved case, protect data before cloud escalation, enable conversational interaction with devices and diagnostics, and allow the team to extend capabilities through plugins. At the end of Phase 2, Androbugger gets measurably smarter with every case the team resolves.

### Prerequisites

All Phase 1 deliverables complete and passing acceptance criteria.

### Task Breakdown

#### 5.1 Privacy Gate

```
Tasks:
  - Implement PII detector in backend/src/androbugger/privacy/gate.py:
    - sanitize(text: str, session_id: str) → SanitizedResult { text, placeholder_count }
    - restore(text: str, session_id: str) → str
    - is_cloud_provider(provider: str) → bool
    - Uses presidio-analyzer with the following recognizers enabled:
      - Built-in: EmailRecognizer, PhoneRecognizer, IpRecognizer, CreditCardRecognizer
      - Custom: see recognizers.py below
    - Uses presidio-anonymizer with operator=Replace, using stable placeholders:
      [EMAIL_1], [EMAIL_2], [IP_1], [MAC_1], [PHONE_1], etc.
    - Counter per entity type per session for stable numbering
  - Implement custom recognizers in backend/src/androbugger/privacy/recognizers.py:
    - MACAddressRecognizer: regex r'([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}'
    - IMEIRecognizer: regex r'\b\d{15}\b' with Luhn check
    - SSIDRecognizer: regex for SSID patterns in logcat (e.g., after 'SSID:', 'ssid=')
    - ADUsernameRecognizer: configurable regex for company AD username format
    - AssetTagRecognizer: configurable regex for company asset tag format (e.g., 'ADV-\d{6}')
    - DeviceSerialRecognizer: regex matching known serial number patterns
    - All custom recognizers registered with presidio-analyzer at startup
    - Admin-configurable: additional regex patterns stored in config, loaded at startup
  - Implement session mapper in backend/src/androbugger/privacy/mapper.py:
    - PlaceholderMapper class:
      - In-memory dict[session_id → dict[placeholder → original]]
      - add_mapping(session_id, placeholder, original) → None
      - get_original(session_id, placeholder) → str | None
      - restore_all(session_id, text) → str (replaces all placeholders with originals)
      - destroy_session(session_id) → None (deletes all mappings for session)
    - Mapper is never persisted to disk
    - Session destruction called on diagnostic session close and on server shutdown
  - Integrate Privacy Gate into LLM router:
    - In router.py complete() and stream():
      - If is_cloud_provider(model): run sanitize() before sending, restore() on response
      - If local provider: bypass gate entirely
      - Log to audit: { action: 'privacy_gate', placeholders_applied: N, provider: X }

Acceptance criteria:
  - Given logcat text containing an email, IP address, MAC address, and a configured asset tag:
    - sanitize() replaces all four with [EMAIL_1], [IP_1], [MAC_1], [ASSET_TAG_1]
    - restore() on a response containing those placeholders returns the original values
  - Given logcat text with no PII: sanitize() returns the text unchanged, placeholder_count=0
  - Cloud LLM call with PII in the prompt: the actual API request (inspectable in audit log)
    contains only placeholders, never original values
  - Local LLM call: Privacy Gate is not invoked (verify via audit log, no privacy_gate action)
  - PlaceholderMapper.destroy_session() removes all mappings: subsequent restore() calls
    return placeholders unchanged
  - Custom recognizers detect all patterns in a test corpus of 50 sample logcat lines
    containing known PII. Target: ≥95% recall, ≤5% false positive rate
```

#### 5.2 Knowledge Layer

```
Tasks:
  - Implement hybrid search store in backend/src/androbugger/knowledge/store.py:
    - class KnowledgeStore:
      - __init__(chroma_path, tantivy_path): initialize both backends
      - add(entry: KnowledgeEntry, content: str, embedding: list[float]) → None
        Adds to both Chroma (vector) and tantivy (BM25 index)
      - search(query: str, query_embedding: list[float], namespace: str | None,
              device_model: str | None, firmware_version: str | None,
              top_k: int = 10) → list[SearchResult]
        Runs both BM25 and vector search, merges results using Reciprocal Rank Fusion (RRF):
          rrf_score = sum(1 / (k + rank_i)) for each result across both retrieval methods
          k = 60 (standard RRF constant)
      - delete(entry_id: str) → None
      - get_stats() → { total_entries, by_namespace: dict[str, int] }
    - SearchResult: { entry_id, title, content_snippet, score, namespace, metadata }
  - Implement embedding generator in backend/src/androbugger/knowledge/embeddings.py:
    - class EmbeddingGenerator:
      - __init__(model_name='nomic-embed-text'): load model via sentence-transformers
      - embed(text: str) → list[float]
      - embed_batch(texts: list[str]) → list[list[float]]
    - Alternative: call Ollama embeddings endpoint if sentence-transformers is too heavy
  - Implement knowledge indexer in backend/src/androbugger/knowledge/indexer.py:
    - index_resolved_diagnosis(session: DiagnosticSession) → str (entry_id)
      Triggered automatically when a diagnostic session is marked 'resolved':
      - Combines: deterministic summary + LLM report + confirmed root cause + applied fix
      - Chunks into sections if content > 2000 tokens
      - Embeds and adds to KnowledgeStore under 'past_diagnoses' namespace
      - Metadata: device_model, firmware_version, root_cause_category, resolved_by, resolved_at
    - index_vendor_document(file_path: str, title: str, metadata: dict) → list[str] (entry_ids)
      For bulk-loading repair manuals, firmware notes, known-issue bulletins:
      - Reads file (markdown, text, PDF via pymupdf)
      - Splits by headers/sections (structural chunking)
      - Embeds and adds to KnowledgeStore under 'vendor_docs' namespace
    - index_aosp_reference(file_path: str, title: str) → list[str]
      Same as vendor but under 'aosp_reference' namespace
    - Background job via arq: runs embedding + indexing asynchronously
  - Integrate knowledge retrieval into diagnostic pipeline:
    - After deterministic summary is generated (step 5 in diagnostic data flow):
      - Embed the summary
      - Search KnowledgeStore filtered by device_model and firmware_version
      - Include top 5 past diagnoses and top 3 vendor KB entries in LLM prompt context
    - Modify build_diagnostic_prompt() in prompts.py to accept knowledge_context parameter
  - Add CLI commands for bulk indexing:
    - `uv run androbugger index-vendor-docs <directory>` → indexes all files in directory
    - `uv run androbugger index-aosp-docs <directory>` → indexes all files in directory
  - Add REST endpoints:
    - GET /api/knowledge/stats → { total_entries, by_namespace }
    - POST /api/knowledge/search { query, namespace, device_model, firmware_version } → { results[] }
    - POST /api/knowledge/index-document { file_path, namespace, title, metadata } → { entry_ids[] }
      (developer+ role)

Acceptance criteria:
  - After resolving a diagnostic session, the case appears in KnowledgeStore and is
    retrievable by searching for keywords from its root cause
  - Hybrid search returns relevant results for both exact queries ("SIGSEGV libfoo.so")
    and semantic queries ("screen freezes during presentation")
  - Search results are filtered by device_model: searching with model "ADV-86" does not
    return results tagged for model "ADV-65"
  - Bulk indexing of a 50-document vendor knowledge base completes in <10 minutes
  - Knowledge context in LLM prompt improves diagnostic relevance: when a previously
    resolved case with the same crash signature exists, the LLM report references it
  - KnowledgeStore handles concurrent reads/writes without corruption
```

#### 5.3 AI Chat Panel

```
Tasks:
  - Implement chat WebSocket endpoint in backend/src/androbugger/api/chat.py:
    - WebSocket /ws/chat/{session_id}:
      - On connect: load diagnostic session context (summary, report, device info)
      - On message from client: { type: 'message', content: str }
        1. Append to chat history (stored in SQLite chat_messages table)
        2. Build prompt: system context + diagnostic summary + chat history + new message
        3. If message references past cases: query Knowledge Layer, add to context
        4. Privacy Gate if cloud provider
        5. Stream LLM response back to client as { type: 'chunk', content: str } messages
        6. On stream complete: send { type: 'done' }
        7. Store assistant response in chat_messages
        8. Run citation verifier on complete response
      - On disconnect: cleanup
    - Chat history is scoped to the diagnostic session — starting a new session starts fresh
    - Maximum chat history in prompt: last 20 messages (truncate oldest if exceeded)
    - Token budget management: diagnostic context + chat history + new message must fit
      within model's context window minus 2000 tokens reserved for response. If history
      exceeds budget, oldest messages are dropped first; if diagnostic context still
      exceeds budget, summarize parsed sections instead of including raw data.
  - Implement POST /api/chat/explain endpoint:
    - Input: { device_serial, selected_lines: list[{line_number, text}] }
    - Builds a focused prompt: "Explain these logcat entries..."
    - Returns { explanation: str, warnings: list[str] }
    - Does NOT create a chat session — this is a one-shot explanation
  - Implement ChatPanel.vue component:
    - Connects to /ws/chat/{session_id}
    - Message input with send button and Enter key support
    - Streams assistant responses with typing indicator
    - Renders markdown in assistant messages (markdown-it)
    - Shows citation verification badges inline
    - "New question" visual separator between exchanges
    - Scrolls to bottom on new messages
    - Shows connection status indicator
  - Integrate ChatPanel into DiagnosticView.vue:
    - Split view: report on left, chat on right (collapsible)
    - Chat panel pre-populated with diagnostic context summary

Acceptance criteria:
  - User can open a diagnostic session and ask follow-up questions in the chat panel
  - Chat maintains context: asking "what about the memory usage?" after a crash diagnosis
    correctly interprets "the" as referring to the current device
  - LLM responses stream in real-time (first chunk appears within 2 seconds for local model)
  - Chat history persists: refreshing the page reloads previous messages
  - "Explain this" on selected logcat lines returns a relevant explanation within 5 seconds
  - Chat works with both local and cloud LLM providers
  - If cloud provider: audit log shows privacy_gate action with placeholder count
```

#### 5.4 Natural Language ADB

```
Tasks:
  - Implement command translation in backend/src/androbugger/api/commands.py:
    - POST /api/commands/natural:
      - Input: { device_serial, query: str }
      - LLM prompt: translate user intent → list of ADB commands
        System prompt instructs LLM to output JSON:
        { commands: [{ cmd: str, args: list[str], destructive: bool, explanation: str }] }
      - For each command, look up permission tier in command_permissions table:
        - Match command against stored glob patterns
        - Determine tier: read_only, state_changing, destructive
        - Check user role against min_role
      - Return: { commands[], needs_confirmation: bool, blocked_commands: list[str] }
    - POST /api/commands/execute:
      - Input: { device_serial, commands: list, confirmed: bool }
      - If needs_confirmation and not confirmed: return 403
      - Execute each command via Device Manager
      - LLM interprets combined output into readable summary
      - Audit log each command
      - Return: { results: list[{ command, output, interpretation }] }
    - POST /api/commands/raw (developer+ role only):
      - Input: { device_serial, command: str }
      - Direct ADB shell execution, no LLM translation
      - Still subject to permission tiers and audit logging
      - Return: { output: str }
  - Implement CommandInput.vue component:
    - Text input with placeholder: "Ask anything about this device..."
    - Submit sends to /api/commands/natural
    - If needs_confirmation: show confirmation dialog listing commands with explanations
    - If blocked_commands: show warning with reason
    - Results rendered as formatted output with LLM interpretation
  - Implement ADB shell terminal for developer role:
    - Use xterm.js in a modal/panel
    - WebSocket connection to backend that proxies adbutils interactive shell
    - Endpoint: WebSocket /ws/shell/{device_serial} (developer+ role only)
    - All input/output logged to audit

Acceptance criteria:
  - "check memory usage" → translates to `adb shell dumpsys meminfo`, executes, returns
    formatted memory breakdown
  - "what apps are crashing" → translates to appropriate logcat filter, returns crash list
  - "clear app data for com.example.app" → identified as state_changing, shows confirmation
    dialog, executes only after user confirms
  - "factory reset this device" → identified as destructive, blocked for technician role,
    allowed for developer role with confirmation
  - Every executed command appears in the audit log with correct user and device
  - Developer role can open xterm.js shell and execute raw ADB commands
```

#### 5.5 Live Logcat Viewer

```
Tasks:
  - Implement logcat streaming endpoint:
    - WebSocket /ws/logcat/{device_serial}:
      - Starts `adb -s {serial} logcat -v threadtime` via adbutils shell_stream
      - Each line parsed into LogcatEntry via parser/logcat.py
      - Sent to client as JSON: { ts, pid, tid, level, tag, msg, raw }
      - Supports client-side filter messages: { type: 'filter', level, tag, pid, keyword }
        Server applies filters to reduce bandwidth
      - On disconnect: kills logcat process
  - Implement LogcatViewer.vue component:
    - Virtual-scrolling log display (handles 100K+ lines without DOM bloat)
      Use a virtual scroll library or PrimeVue VirtualScroller
    - Filter controls: log level dropdown, tag text input, PID text input, keyword search
    - Color coding by log level: V=gray, D=blue, I=green, W=yellow, E=red, F=red-bold
    - Pause/resume button (buffers incoming lines while paused)
    - Line selection: click to select single line, shift+click for range
    - "Explain this" button on selection → calls POST /api/chat/explain
    - "Copy" button on selection → copies raw text to clipboard
    - "Export" button → downloads selected lines or full buffer as .txt
    - Auto-scroll toggle (default on, pauses when user scrolls up)
    - Line count indicator and buffer size warning
  - Integrate into DiagnosticView.vue:
    - Tab or collapsible panel alongside report and chat
    - Logcat stream starts automatically when diagnostic view opens

Acceptance criteria:
  - Logcat stream starts within 2 seconds of opening the viewer
  - Viewer handles 1000 lines/second without browser lag (test with `adb logcat` flood)
  - Filtering by level E+ reduces displayed lines to only errors and fatals
  - Tag filter "ActivityManager" shows only lines with that tag
  - "Explain this" on a selected crash line returns a relevant explanation
  - Pausing stops display updates but does not lose lines (resume shows buffered lines)
  - Export produces a valid .txt file with correct line content
```

#### 5.6 Plugin System

```
Tasks:
  - Define plugin manifest schema (JSON):
    ```json
    {
      "id": "unique-plugin-id",
      "name": "Human Readable Name",
      "version": "1.0.0",
      "author": "Author Name",
      "description": "What this plugin does",
      "min_androbugger_version": "0.2.0",
      "target_devices": ["ADV-*"],
      "target_firmware": [">=4.0.0"],
      "entry_point": "plugin.py",
      "capabilities": {
        "diagnostic_patterns": ["pattern_id_1", "pattern_id_2"],
        "fix_routines": ["fix_id_1"],
        "custom_parsers": ["parser_id_1"]
      },
      "permissions": {
        "adb_commands": ["read_only"],
        "network": false,
        "file_system": ["read"]
      },
      "dependencies": ["numpy>=1.24"],
      "test_data": "test_fixtures/"
    }
    ```
  - Implement plugin loader in backend/src/androbugger/plugins/loader.py:
    - class PluginLoader:
      - __init__(plugin_dir: str): set watch directory (default: backend/plugins/)
      - scan() → list[PluginManifest]: read all manifest.json files in subdirectories
      - load(plugin_id: str) → LoadedPlugin: import entry_point module
      - unload(plugin_id: str) → None
      - watch(): use watchdog library to detect new/modified plugins, trigger validation
    - LoadedPlugin: { manifest, module, status, loaded_at }
  - Implement plugin validator in backend/src/androbugger/plugins/validator.py:
    - class PluginValidator:
      - validate(plugin_path: str) → ValidationResult
      - Stage 1 — Schema check:
        - manifest.json exists and conforms to schema
        - entry_point file exists
        - Required functions are defined in entry_point module:
          - diagnose(parsed_data: dict, device_info: dict) → PluginDiagnosticResult | None
          - Optional: fix(device_serial: str, diagnosis: dict) → FixResult
          - Optional: parse(section_name: str, raw_text: str) → dict
      - Stage 2 — Sandboxed test execution:
        - Load plugin in a subprocess with restricted imports
        - Run diagnose() against sample test data from plugin's test_fixtures/
        - Verify output conforms to PluginDiagnosticResult schema
        - Timeout: 30 seconds
      - Stage 3 — Dependency verification:
        - Parse dependencies from manifest
        - Check each dependency is importable in the current environment
        - If missing: report which dependencies need installing
      - ValidationResult: { passed: bool, stage_results: list[StageResult], errors: list[str] }
  - Implement plugin sandbox in backend/src/androbugger/plugins/sandbox.py:
    - Runtime permission enforcement:
      - Wrap ADB access: plugin can only call commands matching its declared adb_commands tier
      - Block network access if permissions.network is false (via subprocess environment)
      - Restrict file system access to declared paths
    - If a plugin attempts an unpermitted action: log to audit, raise PluginPermissionError
  - Implement plugin API endpoints in backend/src/androbugger/api/plugins.py:
    - GET /api/plugins → list all plugins with status
    - POST /api/plugins/validate { plugin_id } → trigger validation, return result
    - POST /api/plugins/{id}/activate → activate validated plugin
    - POST /api/plugins/{id}/deactivate → deactivate plugin
    - All endpoints require developer+ role
  - Integrate plugins into diagnostic pipeline:
    - After deterministic summary, before LLM call:
      - Iterate active plugins matching the current device model and firmware
      - Call each plugin's diagnose() with parsed data
      - If a plugin returns a result: include it in the diagnostic report and LLM context
    - Plugin-suggested fixes: presented in the UI alongside LLM-suggested fixes,
      same confirmation flow
  - Implement PluginsView.vue:
    - List all plugins with status badges (active/inactive/quarantined/validating)
    - Validation result details (expandable)
    - Activate/deactivate toggles
    - Developer+ role only
  - Create example plugin in backend/plugins/_example_plugin/:
    - Detects a specific crash pattern (e.g., repeated SIGSEGV in a known library)
    - Returns diagnostic result with explanation and suggested fix
    - Includes test_fixtures/ with sample data
    - Serves as the template for plugin developers

Acceptance criteria:
  - Dropping a valid plugin folder into backend/plugins/ triggers automatic detection
  - Validation runs all three stages and reports pass/fail per stage
  - A plugin with a malformed manifest fails Stage 1 with a clear error message
  - A plugin whose diagnose() throws an exception fails Stage 2 without crashing the platform
  - A plugin with a missing dependency fails Stage 3 listing the missing package
  - The example plugin correctly detects its target crash pattern in test data
  - An active plugin's diagnostic output appears in the diagnostic report
  - A plugin declaring read_only ADB access cannot execute a reboot command
  - Plugin activation/deactivation is reflected in the next diagnostic run
  - All plugin actions are audit-logged
```

### Phase 2 Deliverables

```
1. Privacy Gate with standard and custom PII recognizers, integrated into LLM pipeline
2. Knowledge Layer with hybrid BM25 + vector search, auto-indexing of resolved cases
3. AI chat panel with streaming responses and session context
4. Natural language ADB with permission tiers and confirmation flow
5. Live logcat viewer with filtering, selection, and "Explain this"
6. Plugin system with manifest schema, 3-stage validation, runtime sandboxing
7. Example plugin as developer template
8. CLI tools for bulk knowledge base indexing
```

### Phase 2 Success Criteria

```
- PII redaction achieves ≥95% recall on a test corpus of 50 logcat samples
  containing known PII, with ≤5% false positive rate
- Mean time to first useful LLM suggestion: <30 seconds for local model, <8 seconds for cloud
- Knowledge retrieval surfaces relevant past cases: given a bugreport with a previously
  resolved crash signature, the system retrieves the matching case in top 5 results
- >50% of diagnostic sessions complete without cloud LLM escalation
- Plugin validation catches all intentionally broken test plugins (malformed manifest,
  crashing code, missing deps) without crashing the platform
- Chat panel maintains coherent context across 10+ message exchanges
```

## 6. Phase 3: Scale

### Goal

Transform Androbugger from a single-user tool into a team-wide platform with role-based access, multi-device fleet management, firmware comparison, export/reporting, and full audit visibility. At the end of Phase 3, the entire support, QA, and workshop organization uses Androbugger as their standard diagnostic workflow.

### Prerequisites

All Phase 2 deliverables complete and passing acceptance criteria.

### Task Breakdown

#### 6.1 Multi-User Authentication and RBAC

```
Tasks:
  - Implement full user management in backend/src/androbugger/auth/users.py:
    - create_user(username, password, role) → User
    - update_user(user_id, role) → User
    - delete_user(user_id) → None
    - list_users() → list[User]
    - change_password(user_id, old_password, new_password) → None
    - Password hashing: argon2-cffi (argon2id)
    - First-login detection: force_password_change flag on default admin account
  - Implement JWT authentication in backend/src/androbugger/auth/middleware.py:
    - Issue JWT on login with claims: { user_id, username, role, exp }
    - Token expiry: 8 hours (configurable)
    - Refresh token flow: issue refresh token (24h expiry), endpoint to exchange for new access token
    - FastAPI dependency: get_current_user(token) → User
    - FastAPI dependency: require_role(min_role) → decorator
      Role hierarchy: technician < qa_engineer < developer < admin
  - Implement role enforcement across all existing endpoints:
    - Devices: technician+ (all users can see and connect devices)
    - Diagnostics start/view/resolve: technician+
    - Commands natural/execute: technician+ (permission tiers still apply per command)
    - Commands raw: developer+
    - Plugins management: developer+
    - Admin endpoints (users, providers, audit): admin only
    - Knowledge index-document: developer+
  - Implement admin user management UI in AdminView.vue:
    - User list with role badges
    - Create user form (username, password, role)
    - Edit role dropdown
    - Delete user with confirmation
    - Password reset (admin sets temporary password, user forced to change on next login)
  - Implement user session tracking:
    - Store active sessions in memory (not SQLite — ephemeral)
    - Admin can view active sessions and force-logout a user
    - Audit log: login, logout, failed_login, password_change, role_change

Acceptance criteria:
  - Admin can create users with different roles
  - Technician cannot access /api/admin/* endpoints (returns 403)
  - Technician cannot execute POST /api/commands/raw (returns 403)
  - Developer can manage plugins but cannot manage users (returns 403)
  - JWT expiry works: request with expired token returns 401
  - Default admin account forces password change on first login
  - Failed login attempts are audit-logged with IP address
  - Concurrent users (3+) can use the system simultaneously without session conflicts
```

#### 6.2 Multi-Device Dashboard

```
Tasks:
  - Enhance DashboardView.vue:
    - Grid layout of DeviceCard.vue components, responsive (1-4 columns based on viewport)
    - Each DeviceCard shows:
      - Device serial, model, firmware version
      - Connection type icon (USB / wireless)
      - Health indicator: green (no issues), yellow (warnings), red (critical errors)
        Derived from most recent diagnostic session's severity field
      - Last diagnosed timestamp
      - Quick actions: Diagnose, View Last Report, Disconnect
    - Sorting: by serial, model, firmware, health status, last diagnosed
    - Filtering: by model, firmware version, connection type, health status
    - Bulk select: checkbox on each card, "Select All" toggle
  - Implement batch diagnostics:
    - POST /api/diagnostics/batch { device_serials: list[str] } → { session_ids: list[str] }
    - Backend queues one diagnostic job per device via arq
    - Jobs run in parallel (up to configurable concurrency limit, default 3)
    - Frontend shows progress: per-device status (queued/running/completed/failed)
    - Batch results view: summary table with device, severity, root cause, status
  - Implement batch results comparison:
    - GET /api/diagnostics/batch/{batch_id}/summary → { devices: list[DeviceSummary] }
    - DeviceSummary: { serial, model, firmware, severity, top_errors, root_cause, status }
    - Frontend: side-by-side comparison table, sortable by severity
    - Highlight outliers: devices with unique errors not seen in the rest of the batch
  - Implement device health tracking:
    - Background job: after each diagnostic session completes, update device health status
    - Health status derived from latest diagnostic summary:
      - critical: any tombstone or crash loop detected
      - warning: ANR events or thermal throttling detected
      - healthy: no significant issues
    - Health history: store last 10 health statuses per device for trend detection

Acceptance criteria:
  - Dashboard displays 10+ connected devices without UI lag
  - Bulk select 5 devices → batch diagnose → all 5 sessions created and processed
  - Batch results table shows per-device severity and allows sorting
  - Outlier detection flags a device with a unique crash not present on other devices
  - Health indicator updates within 30 seconds of a diagnostic session completing
  - Filtering by firmware version shows only devices running that version
```

#### 6.3 Firmware Comparison Mode

```
Tasks:
  - Implement comparison endpoint:
    - POST /api/diagnostics/compare { session_id_a, session_id_b } → ComparisonReport
    - ComparisonReport:
      - device_a: { serial, model, firmware_version }
      - device_b: { serial, model, firmware_version }
      - new_errors: list of errors present in B but not A (by tag + message pattern)
      - resolved_errors: list of errors present in A but not B
      - common_errors: list of errors present in both
      - severity_change: 'improved' | 'degraded' | 'unchanged'
      - performance_diff: {
          memory_usage_delta_kb: int,
          janky_frames_delta_pct: float,
          crash_count_delta: int,
          anr_count_delta: int,
          thermal_event_count_delta: int
        }
      - llm_analysis: str (LLM-generated narrative comparing the two builds)
    - Error matching logic:
      - Normalize error messages: strip timestamps, PIDs, thread IDs, memory addresses
      - Group by tag + normalized message pattern
      - Match across sessions by pattern similarity (exact match first, then fuzzy with
        difflib.SequenceMatcher threshold 0.85)
  - Implement FirmwareCompare.vue component:
    - Two-column layout: Firmware A (left) vs Firmware B (right)
    - Header: device info and firmware versions for each
    - Sections:
      - New errors (highlighted red): errors only in B
      - Resolved errors (highlighted green): errors only in A
      - Common errors (neutral): errors in both
      - Performance comparison: bar charts or delta indicators for memory, jank, crashes
      - LLM narrative summary at the top
    - Entry point: select two diagnostic sessions from history, or select two devices
      from dashboard and diagnose both, then compare
  - Add comparison access to DiagnosticView.vue:
    - "Compare with..." button → opens session picker → generates comparison

Acceptance criteria:
  - Given two diagnostic sessions from different firmware versions on the same device model:
    - New errors correctly identified (present in B, absent in A)
    - Resolved errors correctly identified (present in A, absent in B)
    - Performance deltas calculated correctly against parsed dumpsys data
  - Error normalization: the same crash with different PIDs/timestamps is matched as the same error
  - LLM analysis provides a coherent narrative of what changed between firmware versions
  - Comparison report renders in <10 seconds for two typical diagnostic sessions
```

#### 6.4 Diagnostic History and Search

```
Tasks:
  - Enhance diagnostic history backend:
    - GET /api/diagnostics/history with query parameters:
      - device_serial: filter by device
      - firmware_version: filter by firmware (exact or prefix match)
      - status: filter by status (running/completed/resolved/failed)
      - severity: filter by severity (critical/warning/info)
      - root_cause_category: filter by category
      - from, to: date range (ISO 8601)
      - page, per_page: pagination (default per_page=20)
      - sort: field name, order: asc/desc
      - Returns: { sessions[], total, page, per_page, pages }
    - GET /api/diagnostics/search:
      - q: full-text search query
      - Searches across: LLM report text, deterministic summary, root cause, applied fix,
        resolution notes
      - Uses SQLite FTS5 for text search
      - Same filters as /history
      - Returns: { sessions[], total, highlights[] }
    - Add FTS5 virtual table:
      ```sql
      CREATE VIRTUAL TABLE diagnostic_search USING fts5(
        session_id,
        llm_report,
        deterministic_summary,
        root_cause,
        applied_fix,
        resolution_notes,
        content='diagnostic_sessions',
        content_rowid='rowid'
      );
      ```
    - Triggers to keep FTS5 in sync with diagnostic_sessions table
  - Implement HistoryView.vue:
    - Search bar with free-text input
    - Filter panel: device serial dropdown, firmware version dropdown, status checkboxes,
      severity checkboxes, date range picker
    - Results table: columns for date, device, firmware, severity, root cause summary, status
    - Click row → navigates to DiagnosticView for that session
    - Pagination controls
    - "Export" button on individual sessions → PDF or markdown download
  - Implement diagnostic statistics dashboard (section in AdminView or standalone):
    - Total sessions by status (pie chart)
    - Sessions over time (line chart, by week/month)
    - Top root cause categories (bar chart)
    - Mean time to resolution (number)
    - Most problematic firmware versions (ranked list)
    - Most problematic device models (ranked list)
    - Uses lightweight charting library: Chart.js via vue-chartjs

Acceptance criteria:
  - Search for "SIGSEGV" returns all sessions where that signal appears in the report
  - Filter by firmware version "4.2.1" shows only sessions from that firmware
  - Date range filter works correctly across timezone boundaries
  - Pagination: navigating to page 3 of 100 results shows results 41-60
  - Statistics dashboard renders within 3 seconds for a database with 500+ sessions
  - FTS5 index stays in sync: resolving a session with new root_cause text is immediately
    searchable
```

#### 6.5 Export and Reporting

```
Tasks:
  - Implement PDF export in backend:
    - POST /api/diagnostics/{id}/export { format: 'pdf' } → binary PDF file
    - PDF generation library: weasyprint (HTML → PDF)
    - Report template (Jinja2 HTML template):
      - Header: Androbugger logo, report title, date, device info
      - Executive summary: severity, root cause, confidence level
      - Deterministic findings: top errors, ANRs, tombstones, thermal events
      - LLM analysis: full diagnostic narrative
      - Evidence: cited log sections with line references
      - Applied fix and outcome (if resolved)
      - Footer: generated by Androbugger, session ID, page numbers
    - Template file: backend/src/androbugger/templates/report.html
  - Implement Markdown export:
    - POST /api/diagnostics/{id}/export { format: 'markdown' } → .md file
    - Same content structure as PDF but in markdown format
    - Includes fenced code blocks for log excerpts
  - Implement ExportDialog.vue:
    - Format selection: PDF or Markdown
    - Preview option (renders in browser before download)
    - Download button → triggers browser file download
  - Add export button to DiagnosticView.vue and HistoryView.vue (per-session)
  - Implement batch export:
    - POST /api/diagnostics/export-batch { session_ids[], format } → zip file
    - Creates one report per session, packages into a zip

Acceptance criteria:
  - PDF export produces a valid, readable PDF with all report sections
  - PDF renders correctly: no overlapping text, tables fit within page width
  - Markdown export produces valid markdown that renders correctly in GitHub
  - Log excerpts in exports preserve formatting (monospace, line numbers)
  - Batch export of 10 sessions produces a zip with 10 individual reports
  - Export completes in <10 seconds for a single session, <60 seconds for a 10-session batch
  - Exported report is self-contained: a reader who was not present can understand
    the diagnosis, evidence, and resolution
```

#### 6.6 Full Audit System

```
Tasks:
  - Enhance audit logging across all Phase 2 and Phase 3 features:
    - Chat messages: log each user message and LLM response (with token count)
    - Plugin actions: load, validate, activate, deactivate, diagnose() call, fix() call
    - Knowledge operations: index, search, delete
    - Export actions: who exported what, when, in what format
    - Batch diagnostics: batch creation, per-device progress, batch completion
    - Firmware comparison: who compared what sessions
    - User management: all CRUD operations on users
  - Implement high-severity audit stream:
    - Separate query: GET /api/admin/audit?severity=critical
    - Auto-populated for: destructive ADB commands, failed login attempts,
      role changes, plugin quarantine events, cloud LLM data transmission
  - Implement audit log viewer in AdminView.vue:
    - Filterable table: by user, action type, severity, device, date range
    - Color-coded severity: info (gray), warning (yellow), critical (red)
    - Expandable detail view for each entry (shows full JSON detail blob)
    - Export audit log as CSV
    - Pagination with configurable page size
  - Implement audit log retention policy:
    - Configurable retention period (default: 90 days)
    - Background job (arq): daily cleanup of entries older than retention period
    - Admin can override: set retention to unlimited
    - Deleted entries are archived to a compressed file before removal

Acceptance criteria:
  - Every user action in the system creates an audit log entry (verify by performing
    each action type and checking the audit table)
  - High-severity stream contains only critical events, no info-level entries
  - Audit viewer loads within 3 seconds for a log with 10,000+ entries
  - CSV export produces a valid CSV with all columns
  - Retention cleanup removes entries older than the configured period
  - Archived entries are recoverable from the compressed archive file
  - After a full diagnostic session with chat, natural language ADB, and export:
    the audit log reconstructs the complete timeline of who did what, when
```

### Phase 3 Deliverables

```
1. Multi-user authentication with JWT and role-based access control (4 roles)
2. Multi-device dashboard with health indicators, sorting, filtering, bulk select
3. Batch diagnostics with parallel processing and outlier detection
4. Firmware comparison mode with error diff and performance delta analysis
5. Full diagnostic history with FTS5 search, filtering, pagination, and statistics
6. PDF and Markdown export with self-contained diagnostic reports
7. Comprehensive audit logging with high-severity stream, viewer, CSV export, and retention
8. Admin dashboard with usage statistics and diagnostic trends
```

### Phase 3 Success Criteria

```
- 3+ concurrent users with different roles can operate the system simultaneously
  without permission leaks, session conflicts, or data corruption
- Batch diagnosis of 10 devices completes within 30 minutes (3 concurrent jobs)
- Firmware comparison correctly identifies ≥90% of new/resolved errors between two builds
  (validated against manual comparison by a QA engineer)
- Full-text search returns relevant results within 1 second for a database with 500+ sessions
- PDF report is accepted by the RMA process without requiring additional documentation
- Audit log can reconstruct the complete action history for any device or user
  over a 30-day period
```

## 7. Phase 4: Evolution

### Goal

Extend Androbugger beyond software diagnostics into hardware diagnostics, fine-tune a local model on the accumulated diagnostic corpus, expose the platform as an MCP server for external tool integration, and open the plugin ecosystem to community contributions. At the end of Phase 4, Androbugger is a full device lifecycle platform and the institutional memory for everything the organization knows about its products.

### Prerequisites

All Phase 3 deliverables complete and passing acceptance criteria. The knowledge base contains at least 50 resolved diagnostic cases to support fine-tuning.

### Task Breakdown

#### 7.1 Fine-Tuning on Diagnostic Corpus

```
Tasks:
  - Implement fine-tuning dataset generator in backend/src/androbugger/llm/finetune.py:
    - export_training_data(min_status='resolved', format='jsonl') → file path
    - For each resolved diagnostic session, generate training pairs:
      - Input: deterministic summary + relevant parsed sections (same format as diagnostic prompt)
      - Output: human-confirmed root cause + applied fix + LLM report (cleaned)
    - Format: JSONL with { messages: [{ role: 'system', content: ... },
      { role: 'user', content: ... }, { role: 'assistant', content: ... }] }
    - Filter options: minimum confidence, specific root cause categories,
      specific device models, date range
    - Data quality checks:
      - Skip sessions where root_cause is empty or generic ("unknown")
      - Skip sessions where applied_fix is empty
      - Deduplicate near-identical cases (same crash signature, same fix)
    - Export statistics: total pairs, per-category breakdown, per-model breakdown
  - Implement fine-tuning pipeline documentation:
    - Step-by-step guide in docs/fine-tuning-guide.md:
      1. Export dataset: `uv run androbugger export-training-data --output training.jsonl`
      2. Validate dataset: `uv run androbugger validate-training-data training.jsonl`
      3. Fine-tune with Unsloth (recommended) or axolotl:
         - Base model: Qwen3 8B or 14B
         - Method: LoRA (rank 16, alpha 32)
         - Training: 3 epochs, learning rate 2e-4, batch size 4
         - Hardware: single GPU with ≥16GB VRAM
      4. Convert to GGUF: `python -m unsloth.save --quantize q4_k_m`
      5. Load into Ollama: `ollama create androbugger-diag -f Modelfile`
      6. Configure as default model in Androbugger admin
    - Modelfile template included in docs/
  - Implement model evaluation harness:
    - `uv run androbugger eval-model --model ollama/androbugger-diag --test-set eval.jsonl`
    - Metrics:
      - Root cause accuracy: does the model identify the same root cause as the human? (exact match)
      - Root cause category accuracy: correct category even if wording differs? (category match)
      - Evidence quality: does the model cite real log lines? (citation verification rate)
      - Fix relevance: is the suggested fix actionable and related to the root cause? (LLM-as-judge)
    - Compare against base model (qwen3:14b) and cloud model (claude-sonnet) on same test set
    - Output: markdown report with per-metric scores and per-case breakdowns
  - Add admin UI for model management:
    - View available models (local + cloud) with performance metrics
    - Set default model per role or per use case
    - Trigger training data export from UI

Acceptance criteria:
  - Dataset export from 50+ resolved cases produces a valid JSONL file with ≥40 training pairs
    (after quality filtering)
  - Fine-tuning guide is complete and reproducible: following the steps produces a working
    GGUF model loadable in Ollama
  - Evaluation harness runs against a 20-case test set and produces a readable comparison report
  - Fine-tuned model achieves ≥10% improvement in root cause category accuracy over base
    Qwen3 model on the test set (this is the minimum bar to justify deployment)
  - Fine-tuned model loads and serves via Ollama without errors
```

#### 7.2 Hardware Diagnostics

```
Tasks:
  - Implement hardware data collectors in backend/src/androbugger/device/hardware.py:
    - collect_sensor_data(serial) → SensorData
      - ADB commands: `dumpsys sensorservice`, `cat /sys/class/thermal/thermal_zone*/temp`
      - Parsed into: { sensors: list[{ name, type, value, unit, status }],
        thermal_zones: list[{ zone, temp_c, trip_points }] }
    - collect_display_info(serial) → DisplayInfo
      - ADB commands: `dumpsys display`, `dumpsys SurfaceFlinger`, `wm size`, `wm density`
      - Parsed into: { resolution, density, refresh_rate, hdr_support, color_mode,
        connected_displays: list, surface_stats }
    - collect_touch_data(serial) → TouchInfo
      - ADB commands: `getevent -lp`, `dumpsys input`
      - Parsed into: { touch_devices: list[{ name, protocol, axes, status }],
        input_dispatcher_state, pending_events_count }
    - collect_storage_health(serial) → StorageHealth
      - ADB commands: `df`, `dumpsys diskstats`, `sm list-volumes`
      - Parsed into: { partitions: list[{ mount, total_kb, used_kb, available_kb }],
        io_stats, emmc_health_pct (if available via /sys/class/mmc_host/) }
    - collect_network_info(serial) → NetworkInfo
      - ADB commands: `dumpsys connectivity`, `dumpsys wifi`, `ip addr`
      - Parsed into: { interfaces: list[{ name, state, ip, mac }],
        wifi: { ssid, signal_strength, frequency }, ethernet: { state, speed } }
    - collect_usb_info(serial) → USBInfo
      - ADB commands: `dumpsys usb`, `lsusb` (if available)
      - Parsed into: { ports: list[{ id, mode, connected_device }], otg_supported }
  - Implement hardware diagnostic summary in backend/src/androbugger/parser/hardware_summary.py:
    - generate_hardware_summary(sensor, display, touch, storage, network, usb) → HardwareSummary
    - HardwareSummary:
      - thermal_status: 'normal' | 'warm' | 'critical' (based on zone temps vs trip points)
      - storage_status: 'healthy' | 'warning' | 'critical' (based on available space and eMMC health)
      - touch_status: 'responsive' | 'degraded' | 'unresponsive' (based on input device state)
      - display_status: 'normal' | 'misconfigured' | 'error' (based on display info anomalies)
      - network_status: 'connected' | 'limited' | 'disconnected'
      - anomalies: list[{ component, description, severity }]
  - Integrate hardware diagnostics into the diagnostic pipeline:
    - Option 1: "Full Diagnosis" button runs both software (bugreport) and hardware collectors
    - Option 2: "Hardware Check" button runs only hardware collectors (faster, no bugreport)
    - Hardware summary included in LLM prompt when performing full diagnosis
    - Hardware findings appear as a separate section in the diagnostic report
  - Implement hardware-specific LLM prompt template in prompts.py:
    - HARDWARE_DIAGNOSTIC_PROMPT: instructs LLM to correlate hardware state with software issues
      (e.g., thermal throttling causing UI freezes, low storage causing app crashes)
  - Add hardware section to DiagnosticReport.vue:
    - Visual indicators for each hardware subsystem (green/yellow/red)
    - Expandable detail for each subsystem
    - Anomalies highlighted with explanations
  - Implement basic hardware test routines:
    - Touch test: `input tap` at grid points, verify via `getevent` that touches register
    - Display test: push and display test patterns (color bars, gradient, dead pixel check)
      via `am start` with a test APK or `screencap` comparison
    - Network test: ping gateway, DNS resolution, measure latency
    - Storage test: write/read speed via `dd` with small test file
    - Each test returns: { test_name, passed: bool, result_detail, duration_ms }
    - All tests are read-only and non-destructive

Acceptance criteria:
  - Hardware data collection completes within 30 seconds for all subsystems
  - Thermal zone parsing correctly reads temperature values and trip points
  - Storage health correctly calculates available space percentages
  - Touch info correctly identifies connected touch input devices
  - Hardware summary correctly flags anomalies:
    - Thermal zone above trip point → thermal_status = 'critical'
    - Storage <5% free → storage_status = 'critical'
    - No touch input devices found → touch_status = 'unresponsive'
  - Full diagnosis (software + hardware) report includes both sections
  - Hardware test routines execute without modifying device state
  - Touch test detects a non-responsive touch zone (simulated by disconnecting digitizer)
```

#### 7.3 MCP Server Interface

```
Tasks:
  - Implement MCP server in backend/src/androbugger/mcp/server.py:
    - Protocol: Model Context Protocol (MCP) over stdio or SSE transport
    - Library: mcp Python SDK (modelcontextprotocol/python-sdk)
    - Exposed tools:
      - androbugger_list_devices() → list of connected devices with info
      - androbugger_diagnose(device_serial) → diagnostic report (markdown)
      - androbugger_get_report(session_id) → full diagnostic report
      - androbugger_logcat(device_serial, lines=100, level='W') → recent logcat entries
      - androbugger_shell(device_serial, command) → command output
        (subject to same permission tiers as internal commands)
      - androbugger_search_knowledge(query) → matching past cases and KB entries
      - androbugger_device_info(device_serial) → detailed device properties
      - androbugger_hardware_check(device_serial) → hardware diagnostic summary
      - androbugger_compare(session_id_a, session_id_b) → firmware comparison report
    - Authentication: API key passed as environment variable, validated on connection
    - Audit logging: all MCP tool invocations logged with the same audit system
  - Implement MCP server entry point:
    - `uv run androbugger mcp-server --transport stdio` for Claude Desktop / Claude Code
    - `uv run androbugger mcp-server --transport sse --port 8765` for network access
    - Add to docker-compose.yml as optional service
  - Create MCP configuration documentation:
    - docs/mcp-integration.md:
      - Claude Desktop: claude_desktop_config.json snippet
      - Claude Code: .mcp.json snippet
      - Cursor: MCP settings configuration
      - Authentication setup
      - Available tools with descriptions and example usage
  - Implement MCP server tests:
    - Test each tool with mock device data
    - Test permission enforcement (shell commands respect tiers)
    - Test authentication (invalid key rejected)

Acceptance criteria:
  - Claude Desktop can connect to Androbugger MCP server and list connected devices
  - Claude Code can trigger a diagnosis via MCP and receive the report
  - MCP shell command respects permission tiers: destructive commands require confirmation
    (returned as tool result asking user to confirm in Androbugger UI)
  - MCP search_knowledge returns relevant past cases
  - All MCP tool invocations appear in the audit log
  - MCP server handles concurrent connections from multiple AI assistants
  - Documentation is sufficient for a developer to configure MCP integration in <10 minutes
```

#### 7.4 Community Plugin Ecosystem

```
Tasks:
  - Create plugin developer guide in docs/plugin-developer-guide.md:
    - Getting started: creating a plugin from the example template
    - Manifest reference: every field explained with examples
    - Plugin API reference:
      - diagnose(parsed_data, device_info) → PluginDiagnosticResult
      - fix(device_serial, diagnosis) → FixResult
      - parse(section_name, raw_text) → dict
    - Available context: what data the plugin receives (parsed bugreport sections,
      device info, diagnostic summary)
    - Permission model: what each permission level allows
    - Testing: how to write test fixtures, how to run validation locally
    - Packaging: how to structure the plugin folder for distribution
    - Best practices: error handling, logging, performance considerations
  - Create plugin template repository:
    - GitHub template repo: androbugger-plugin-template
    - Includes: manifest.json skeleton, plugin.py with stub functions,
      test_fixtures/ with sample data, README.md with instructions
    - One-command setup: `gh repo create my-plugin --template androbugger-plugin-template`
  - Implement plugin marketplace (simple):
    - GitHub-based: plugins listed as repositories with the topic `androbugger-plugin`
    - GET /api/plugins/marketplace → fetches GitHub API for repos with that topic
    - Returns: { plugins: list[{ name, description, author, stars, url, version }] }
    - "Install" button in PluginsView.vue: clones repo into backend/plugins/ and triggers validation
    - No auto-update: admin manually pulls new versions
  - Implement plugin contribution guidelines:
    - CONTRIBUTING.md in main repo
    - Plugin review checklist: manifest valid, tests pass, no unnecessary permissions,
      no hardcoded paths, documentation included
    - License compatibility requirements (MIT, Apache 2.0, or compatible)
  - Create 3 reference plugins beyond the example:
    - Plugin: firmware-version-checker
      - Detects known-bad firmware versions from a maintained list
      - Returns warning with link to firmware update instructions
    - Plugin: memory-leak-detector
      - Analyzes dumpsys meminfo snapshots over time (if multiple bugreports available)
      - Identifies processes with monotonically increasing PSS
    - Plugin: crash-pattern-matcher
      - Maintains a library of known crash signatures (signal + library + function)
      - Matches tombstones against the library and returns known fixes

Acceptance criteria:
  - Plugin developer guide is sufficient for a Python developer to create a working plugin
    in <2 hours (validated by having one team member follow the guide)
  - Template repository produces a valid plugin skeleton that passes validation out of the box
  - Marketplace endpoint returns plugin listings from GitHub
  - "Install" from marketplace clones the repo and triggers validation successfully
  - All 3 reference plugins pass validation and produce correct results on test data
  - Reference plugins demonstrate all three capability types: diagnostic_patterns,
    fix_routines, custom_parsers
```

#### 7.5 Screen Mirroring

```
Tasks:
  - Implement scrcpy integration in backend/src/androbugger/device/scrcpy.py:
    - class ScrcpyManager:
      - start(serial, quality=50, max_fps=30, max_size=1280) → stream_id
        Launches scrcpy subprocess with:
        `scrcpy -s {serial} --no-window --video-codec=h264 --record=/tmp/{stream_id}.mp4
         --max-fps={max_fps} --max-size={max_size} -b {quality}k`
        Or use scrcpy's --v4l2-sink or --tcpip forwarding for frame access
      - stop(stream_id) → None: kills subprocess
      - get_frame(stream_id) → JPEG bytes: latest frame capture
      - is_running(stream_id) → bool
    - Alternative approach if real-time streaming is too complex for Phase 4:
      - Periodic screencap: `adb -s {serial} exec-out screencap -p` every 500ms
      - Lower frame rate but no scrcpy dependency for basic mirroring
  - Implement screen mirror WebSocket endpoint:
    - WebSocket /ws/scrcpy/{device_serial}:
      - On connect: start ScrcpyManager for the device
      - Stream frames as binary WebSocket messages (JPEG)
      - Target frame rate: 10-30 fps depending on quality setting
      - On disconnect: stop ScrcpyManager
  - Implement ScreenMirror.vue component:
    - Canvas or img element displaying the latest frame
    - Renders in a resizable panel within DiagnosticView.vue
    - Quality/FPS controls
    - Screenshot button: saves current frame as PNG
    - Picture-in-picture mode: small floating window while working in other views
    - Aspect ratio preservation
  - Integrate with logcat viewer:
    - Side-by-side layout option: screen mirror left, logcat right
    - Timestamp correlation: clicking a logcat entry highlights the approximate
      moment in the screen recording (if recording is active)

Acceptance criteria:
  - Screen mirror displays the panel's current screen in the browser
  - Frame rate is ≥10 fps at 720p quality on a local network connection
  - Screenshot captures a clear, full-resolution image
  - Mirror starts within 3 seconds of opening the viewer
  - Mirror works over both USB and wireless ADB connections
  - Stopping the mirror releases all system resources (no orphaned scrcpy processes)
  - Browser memory usage stays stable during extended mirroring sessions (no frame buffer leak)
```

#### 7.6 Advanced Diagnostic Features

```
Tasks:
  - Implement scheduled diagnostics:
    - Configurable per-device schedule: run bugreport + parse + summary on a cron
    - arq scheduled jobs: daily, weekly, or custom interval
    - Store results as diagnostic sessions with source='scheduled'
    - Regression detection: compare latest scheduled result against previous
      - Alert if new error categories appear
      - Alert if crash count increases beyond threshold
      - Alert if thermal events increase
    - Notification: WebSocket push to connected clients, stored in notification table
  - Implement diagnostic session templates:
    - Named diagnostic profiles: "Quick Check" (logcat + top errors only),
      "Full Software" (bugreport + all parsers), "Full + Hardware" (everything),
      "QA Regression" (bugreport + firmware comparison against baseline)
    - Stored in config, selectable from UI when starting a diagnosis
    - POST /api/diagnostics/start { device_serial, template: str }
  - Implement device groups:
    - Group devices by purpose: "QA Fleet", "RMA Queue", "Development"
    - CRUD endpoints: /api/device-groups/*
    - Dashboard filtering by group
    - Batch operations scoped to groups
  - Implement notification system:
    - In-app notifications (not email/SMS):
      - Diagnostic session completed
      - Regression detected in scheduled scan
      - Plugin validation completed
      - Cloud LLM budget threshold reached (80%, 100%)
    - WebSocket /ws/notifications: push notifications to connected clients
    - Notification bell icon in UI header with unread count
    - Mark as read / dismiss actions

Acceptance criteria:
  - Scheduled diagnostic runs at configured interval and stores results
  - Regression detection correctly flags a new crash category not present in previous scan
  - Diagnostic templates produce different scopes of analysis (Quick Check is faster than Full)
  - Device groups correctly filter dashboard and scope batch operations
  - Notifications appear in real-time for connected users
  - Budget threshold notification fires when cloud spending reaches 80%
```

### Phase 4 Deliverables

```
1. Fine-tuning pipeline: dataset export, training guide, evaluation harness
2. Hardware diagnostics: sensor data, display info, touch, storage, network, USB
3. Hardware test routines: touch, display, network, storage
4. MCP server interface with 9 exposed tools and authentication
5. Community plugin ecosystem: developer guide, template repo, marketplace, 3 reference plugins
6. Screen mirroring with live view, screenshot, and logcat correlation
7. Scheduled diagnostics with regression detection
8. Diagnostic templates and device groups
9. In-app notification system
```

### Phase 4 Success Criteria

```
- Fine-tuned model demonstrates ≥10% improvement in root cause category accuracy
  over base model on a 20-case test set
- Hardware diagnostics correctly identify thermal, storage, touch, and display anomalies
  on devices with known hardware issues (validated by workshop staff)
- MCP server integrates with Claude Desktop and Claude Code without manual workarounds
- At least 1 community-contributed plugin is submitted and passes validation within
  3 months of ecosystem launch
- Screen mirroring runs at ≥10 fps over local network with <200ms latency
- Scheduled diagnostics catch a firmware regression before it is reported by a user
  (validated over a 1-month trial)
- The system contains ≥100 resolved cases in the knowledge base and retrieval
  noticeably improves diagnostic speed for recurring issue types
```

## 8. Plugin System Specification

### Overview

The plugin system allows anyone to extend Androbugger's diagnostic capabilities by dropping a Python module into a watched directory. Plugins can detect specific error patterns, provide custom parsers for non-standard log formats, and execute automated fixes. Every plugin is validated before activation and sandboxed at runtime. Plugin-provided features appear alongside built-in features in the web UI with the same permission and audit controls.

### Plugin Directory Structure

```
backend/plugins/
├── _example_plugin/                # Ships with Androbugger as a reference
│   ├── manifest.json
│   ├── plugin.py
│   ├── README.md
│   └── test_fixtures/
│       ├── input_bugreport.json    # Sample parsed bugreport data
│       └── expected_output.json    # Expected diagnose() output
├── firmware-version-checker/       # Reference plugin
│   ├── manifest.json
│   ├── plugin.py
│   ├── known_bad_versions.json
│   ├── README.md
│   └── test_fixtures/
│       ├── input_bugreport.json
│       └── expected_output.json
└── my-custom-plugin/               # User-created plugin
    ├── manifest.json
    ├── plugin.py
    └── test_fixtures/
        └── ...
```

Each plugin lives in its own subdirectory under `backend/plugins/`. The directory name serves as the plugin ID. Directories starting with `_` are treated as examples and are not auto-loaded on startup (they must be manually activated).

### Manifest Schema

Every plugin must contain a `manifest.json` at its root. The manifest declares what the plugin does, what it needs, and what it is allowed to access.

```json
{
  "$schema": "https://androbugger.dev/schemas/plugin-manifest-v1.json",
  "id": "unique-plugin-id",
  "name": "Human Readable Plugin Name",
  "version": "1.0.0",
  "author": "Author Name <author@example.com>",
  "description": "One-paragraph description of what this plugin does.",
  "license": "MIT",
  "min_androbugger_version": "0.2.0",
  "target_devices": {
    "models": ["ADV-86*", "ADV-75*"],
    "firmware_versions": [">=4.0.0", "<6.0.0"]
  },
  "entry_point": "plugin.py",
  "capabilities": {
    "diagnostic_patterns": [
      {
        "id": "pattern_sigsegv_libfoo",
        "name": "SIGSEGV in libfoo.so",
        "description": "Detects repeated SIGSEGV crashes in the libfoo shared library",
        "severity": "critical"
      }
    ],
    "fix_routines": [
      {
        "id": "fix_clear_libfoo_cache",
        "name": "Clear libfoo cache",
        "description": "Clears the corrupted cache that causes SIGSEGV in libfoo",
        "destructive": false,
        "requires_confirmation": true
      }
    ],
    "custom_parsers": [
      {
        "id": "parser_custom_vendor_log",
        "name": "ADVANTouch vendor log parser",
        "description": "Parses the proprietary ADVANTouch system health log format",
        "target_section": "VENDOR_HEALTH_LOG"
      }
    ]
  },
  "permissions": {
    "adb_commands": "read_only",
    "network": false,
    "file_system": "read",
    "max_execution_time_seconds": 60
  },
  "dependencies": [
    "numpy>=1.24"
  ],
  "test_data": "test_fixtures/"
}
```

#### Manifest Field Reference

```
id (required, string)
  Unique identifier. Must match the directory name. Lowercase alphanumeric and hyphens only.
  Regex: ^[a-z0-9][a-z0-9-]{2,48}[a-z0-9]$

name (required, string)
  Human-readable display name. Max 100 characters.

version (required, string)
  Semantic version: MAJOR.MINOR.PATCH

author (required, string)
  Author name and optional email.

description (required, string)
  One-paragraph description. Max 500 characters.

license (required, string)
  SPDX license identifier. Must be compatible with Androbugger's license.

min_androbugger_version (required, string)
  Minimum Androbugger version this plugin supports. Semver range.

target_devices (optional, object)
  models (list[string]): glob patterns for device model names. Default: ["*"] (all models).
  firmware_versions (list[string]): semver ranges. Default: ["*"] (all versions).
  If a device does not match both model and firmware, the plugin is skipped for that device.

entry_point (required, string)
  Relative path to the Python file containing the plugin class. Must be within the plugin directory.

capabilities (required, object)
  At least one of diagnostic_patterns, fix_routines, or custom_parsers must be non-empty.

  diagnostic_patterns (list[object]):
    id (string): unique within this plugin
    name (string): human-readable name
    description (string): what this pattern detects
    severity (string): 'info' | 'warning' | 'critical'

  fix_routines (list[object]):
    id (string): unique within this plugin
    name (string): human-readable name
    description (string): what this fix does
    destructive (bool): whether the fix modifies device state in a way that cannot be undone
    requires_confirmation (bool): whether user confirmation is required before execution

  custom_parsers (list[object]):
    id (string): unique within this plugin
    name (string): human-readable name
    description (string): what this parser handles
    target_section (string): bugreport section name this parser applies to

permissions (required, object)
  adb_commands (string): 'none' | 'read_only' | 'state_changing' | 'destructive'
    Determines which ADB commands the plugin may invoke via the sandbox API.
    Default: 'none'. Most diagnostic plugins need only 'read_only' or 'none'.
  network (bool): whether the plugin may make outbound network requests. Default: false.
  file_system (string): 'none' | 'read' | 'read_write'
    Scope is restricted to the plugin's own directory and /tmp. Default: 'none'.
  max_execution_time_seconds (int): timeout for diagnose() and fix() calls. Default: 60.

dependencies (optional, list[string])
  Python package requirements in pip format. Validated during Stage 3 of the validation protocol.

test_data (optional, string)
  Relative path to test fixtures directory. Required if the plugin declares diagnostic_patterns.
```

### Plugin Entry Point API

The entry point file must define a class named `Plugin` that implements one or more of the following methods:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class PluginDiagnosticResult:
    """Returned by diagnose() when a pattern is detected."""
    pattern_id: str                # Must match a declared diagnostic_patterns[].id
    detected: bool                 # True if the pattern was found
    confidence: str                # 'low' | 'medium' | 'high'
    summary: str                   # One-line summary for the diagnostic report
    detail: str                    # Full explanation (markdown)
    evidence: list[dict]           # List of { section, line_number, text } references
    suggested_fix_id: Optional[str] = None  # If a fix_routine handles this, reference its ID


@dataclass
class FixResult:
    """Returned by fix() after attempting an automated fix."""
    fix_id: str                    # Must match a declared fix_routines[].id
    success: bool
    detail: str                    # What was done (or what went wrong)
    commands_executed: list[str]   # ADB commands that were executed
    requires_reboot: bool = False


class Plugin:
    """
    Androbugger Plugin Interface.

    All methods receive a `context` dict with:
      - device_info: { serial, model, firmware_version, android_version }
      - adb: sandbox ADB client (respects declared permissions)
      - logger: plugin-scoped logger
    """

    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        """
        Analyze parsed bugreport data and return detected patterns.

        Args:
            parsed_data: {
                'summary': DiagnosticSummary dict,
                'logcat': list of LogcatEntry dicts,
                'anr_traces': list of ANRTrace dicts,
                'tombstones': list of Tombstone dicts,
                'dumpsys': { 'meminfo': dict, 'batterystats': dict, ... },
                'dmesg': list of DmesgEntry dicts,
                'custom_sections': { section_name: raw_text }  # for custom parsers
            }
            context: see class docstring

        Returns:
            List of PluginDiagnosticResult for each pattern checked.
            Return empty list if no patterns detected.
            Return result with detected=False to explicitly report a pattern was checked but not found.
        """
        return []

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult,
            context: dict) -> Optional[FixResult]:
        """
        Attempt to apply an automated fix for a detected pattern.

        Only called if:
          1. diagnose() returned a result with a suggested_fix_id
          2. The fix_routine is declared in the manifest
          3. The user confirmed execution in the UI

        Args:
            device_serial: target device
            diagnosis: the PluginDiagnosticResult that triggered this fix
            context: see class docstring

        Returns:
            FixResult describing the outcome. None if fix is not applicable.
        """
        return None

    def parse(self, section_name: str, raw_text: str,
              context: dict) -> Optional[dict]:
        """
        Parse a custom or non-standard bugreport section.

        Only called if the section_name matches a declared custom_parsers[].target_section.

        Args:
            section_name: name of the bugreport section
            raw_text: raw text content of the section
            context: see class docstring

        Returns:
            Parsed data as a dict. Structure is plugin-defined.
            This data is added to parsed_data['custom_sections'][section_name]
            and made available to diagnose().
            None if the section could not be parsed.
        """
        return None
```

### Validation Protocol

When a plugin is detected (new directory or modified manifest), the platform runs a three-stage validation before allowing activation.

```
Stage 1: Schema Check
  Input: manifest.json
  Checks:
    - File exists and is valid JSON
    - All required fields are present with correct types
    - id matches directory name
    - id matches regex: ^[a-z0-9][a-z0-9-]{2,48}[a-z0-9]$
    - version is valid semver
    - min_androbugger_version is satisfied by current Androbugger version
    - entry_point file exists at declared path
    - entry_point file defines a class named Plugin
    - Plugin class has at least one of: diagnose(), fix(), parse()
    - Every diagnostic_patterns[].id is unique
    - Every fix_routines[].id is unique
    - Every custom_parsers[].id is unique
    - If diagnostic_patterns is non-empty, test_data must be declared and directory must exist
    - permissions.adb_commands is a valid tier
    - license is a recognized SPDX identifier
  Result: PASS or FAIL with list of specific errors

Stage 2: Sandboxed Test Execution
  Precondition: Stage 1 passed
  Input: entry_point module + test_fixtures/
  Execution:
    - Import the plugin module in a subprocess with:
      - Restricted import whitelist (no os.system, no subprocess, no socket unless network=true)
      - Working directory set to plugin directory
      - Timeout: max_execution_time_seconds from manifest (default 60)
    - Load test fixtures:
      - input_bugreport.json → parsed_data dict
      - expected_output.json → expected results (optional, used for output validation)
    - Call plugin.diagnose(parsed_data, mock_context) where mock_context provides:
      - device_info: { serial: 'TEST-000', model: 'ADV-TEST', firmware_version: '0.0.0' }
      - adb: mock ADB client that returns predefined responses
      - logger: captures log output
    - Validate output:
      - Return type is list[PluginDiagnosticResult] (or compatible dict)
      - Each result has all required fields
      - Each pattern_id references a declared diagnostic_patterns[].id
      - Each suggested_fix_id (if set) references a declared fix_routines[].id
      - If expected_output.json exists: compare detected patterns against expected
    - If fix routines are declared and test_fixtures include fix test data:
      - Call plugin.fix(serial, diagnosis, mock_context)
      - Validate FixResult structure
    - If custom_parsers are declared and test_fixtures include raw section text:
      - Call plugin.parse(section_name, raw_text, mock_context)
      - Validate return is dict or None
  Result: PASS or FAIL with:
    - stdout/stderr captured from subprocess
    - Exception traceback if plugin crashed
    - Output validation errors
    - Execution time

Stage 3: Dependency Verification
  Precondition: Stage 2 passed
  Input: manifest.dependencies list
  Checks:
    - For each dependency string (e.g., "numpy>=1.24"):
      - Parse package name and version constraint
      - Check if package is importable in the current Python environment
      - Check if installed version satisfies the constraint
    - If any dependency is missing or version-incompatible:
      - Report which packages need to be installed
      - Provide the pip/uv install command
  Result: PASS or FAIL with list of missing/incompatible dependencies
```

### Validation Result Actions

```
All 3 stages PASS:
  - Plugin status set to 'inactive' (ready for activation)
  - Admin/developer can activate via UI or API
  - Validation result stored in plugins table

Any stage FAIL:
  - Plugin status set to 'quarantined'
  - Detailed error report stored in plugins table validation_result column
  - Plugin is NOT loadable until errors are fixed and re-validation passes
  - Notification sent to admin users
```

### Runtime Permission Enforcement

When a plugin is active and its methods are called during a diagnostic session, the sandbox enforces the declared permissions:

```
ADB Command Enforcement:
  permission: 'none'
    - context.adb is None — plugin has no ADB access
  permission: 'read_only'
    - context.adb.shell() allows only: logcat, dumpsys, getprop, ps, top, df, cat (select paths),
      ls, stat, wm, input (read), screencap
    - context.adb.shell() blocks: pm clear, pm install, am force-stop, reboot, rm, mv, cp,
      settings put, svc, setprop, and any unrecognized command
    - Blocked command: raises PluginPermissionError, logged to audit
  permission: 'state_changing'
    - Allows read_only commands plus: pm clear, am force-stop, settings put, svc wifi enable/disable
    - Blocks: reboot, rm, factory reset, pm install, setprop
  permission: 'destructive'
    - Allows all commands (same as developer role)
    - Plugin must declare requires_confirmation: true on all fix routines

Network Enforcement:
  network: false
    - Outbound network calls from the plugin subprocess are blocked via environment variable
      that configures the sandbox HTTP proxy to reject all requests
    - Socket creation attempts raise PluginPermissionError
  network: true
    - Outbound network calls are allowed
    - All outbound requests are logged to audit

File System Enforcement:
  file_system: 'none'
    - Plugin can only access in-memory data passed to its methods
  file_system: 'read'
    - Plugin can read files within its own directory and /tmp
    - Reads outside these paths raise PluginPermissionError
  file_system: 'read_write'
    - Plugin can read/write within its own directory and /tmp
    - Access outside these paths raises PluginPermissionError

Execution Time Enforcement:
  - Each method call (diagnose, fix, parse) is wrapped in a timeout
  - If max_execution_time_seconds is exceeded: method is terminated,
    PluginTimeoutError raised, logged to audit
  - Plugin is NOT automatically deactivated on timeout — it may succeed on different input
  - Repeated timeouts (3 consecutive) trigger a warning notification to admin
```

### Plugin Lifecycle

```
1. DETECTED    — New directory appears in backend/plugins/
2. VALIDATING  — Validation protocol running (3 stages)
3. QUARANTINED — Validation failed (manual fix required, then re-validate)
   OR
   INACTIVE    — Validation passed, waiting for activation
4. ACTIVE      — Plugin is loaded and participates in diagnostic pipeline
5. INACTIVE    — Deactivated by admin/developer (can be reactivated without re-validation
                  unless manifest has changed)

State transitions:
  DETECTED → VALIDATING           (automatic on detection)
  VALIDATING → INACTIVE           (all stages pass)
  VALIDATING → QUARANTINED        (any stage fails)
  QUARANTINED → VALIDATING        (triggered manually after fix)
  INACTIVE → ACTIVE               (activated by admin/developer)
  ACTIVE → INACTIVE               (deactivated by admin/developer)
  ACTIVE → VALIDATING             (manifest.json modified while active — re-validate)
  * → DETECTED                    (plugin directory deleted and re-created)
```

### Integration with Diagnostic Pipeline

```
During a diagnostic session, after the deterministic summary is generated:

1. Get active plugins: SELECT * FROM plugins WHERE status = 'active'
2. Filter by device: match device model against plugin target_devices.models,
   match firmware against target_devices.firmware_versions
3. For matching plugins with custom_parsers:
   - For each custom_sections in the bugreport not handled by built-in parsers:
     - If a plugin declares a custom_parser for that section: call plugin.parse()
     - Store result in parsed_data['custom_sections']
4. For matching plugins with diagnostic_patterns:
   - Call plugin.diagnose(parsed_data, context)
   - Collect all PluginDiagnosticResult entries
5. Include plugin results in:
   - The deterministic summary (appended as 'plugin_findings' section)
   - The LLM prompt context (so the LLM can incorporate plugin insights)
   - The diagnostic report (rendered as a separate 'Plugin Analysis' section)
6. If any plugin result includes a suggested_fix_id:
   - Present the fix alongside LLM-suggested fixes in the UI
   - Same confirmation flow: user must approve before execution
   - On approval: call plugin.fix(serial, diagnosis, context)
   - Log fix attempt and result to audit
   - Store fix result in diagnostic session
```

## 9. Testing & Quality Assurance

### Testing Layers

```
Layer 1: Unit Tests (pytest)
  Scope: individual functions and classes in isolation
  Location: backend/tests/test_<module>/
  Mocking: all external dependencies (ADB, LLM, filesystem, database) are mocked
  Coverage target: ≥80% line coverage on parser/, privacy/, knowledge/, auth/ modules
  Run: `uv run pytest backend/tests/ -x --cov=androbugger`

Layer 2: Integration Tests (pytest + docker)
  Scope: module interactions — parser + knowledge, privacy + LLM router, device + parser
  Location: backend/tests/integration/
  Dependencies: SQLite (real, in-memory), Chroma (real, ephemeral), Ollama (real, test model)
  Uses a lightweight local model (qwen3:0.6b or phi-4-mini) to keep tests fast
  Run: `uv run pytest backend/tests/integration/ --integration`

Layer 3: End-to-End Tests (Playwright)
  Scope: full user workflows through the browser
  Location: frontend/e2e/
  Dependencies: full Docker Compose stack running
  Tests:
    - Login → see dashboard → connect device (mock) → diagnose → view report → resolve
    - Login → open logcat viewer → filter → explain selection
    - Login → natural language ADB → confirm command → view result
    - Login as admin → create user → assign role → verify permissions
    - Login → chat panel → ask follow-up → verify streaming response
  Run: `cd frontend && npx playwright test`

Layer 4: Parser Accuracy Tests
  Scope: validate parsers against known-good bugreport samples
  Location: backend/tests/test_parser/
  Fixtures: real (anonymized) bugreport samples in backend/tests/fixtures/
  Method:
    - For each sample bugreport, a corresponding expected_output.json contains
      manually verified parsed data
    - Tests compare parser output against expected output
    - Tolerance: structural match required, timestamp precision within 1 second
  Minimum fixture set:
    - 5 bugreport zips from different ADVANTouch models and firmware versions
    - 10 logcat samples covering: normal operation, crash, ANR, thermal, OOM
    - 5 ANR trace files
    - 5 tombstone files
    - 5 dumpsys meminfo outputs, 5 dumpsys batterystats outputs

Layer 5: Privacy Gate Tests
  Scope: PII detection recall and false positive rate
  Location: backend/tests/test_privacy/
  Fixtures: backend/tests/fixtures/pii_test_corpus/
    - 50 logcat samples with manually labeled PII entities
    - Labels: { line_number, entity_type, start_char, end_char, original_value }
  Metrics:
    - Recall: (detected PII / total PII) ≥ 95%
    - Precision: (true PII / all detections) ≥ 95%
    - Roundtrip: sanitize → restore produces original text exactly
  Run: `uv run pytest backend/tests/test_privacy/ --pii-report`

Layer 6: LLM Output Quality Tests
  Scope: diagnostic accuracy of LLM-generated reports
  Location: backend/tests/test_llm/
  Method:
    - Curate 20 resolved diagnostic cases as the evaluation set
    - Each case: { input_bugreport, expected_root_cause_category, expected_evidence_sections }
    - Run the full diagnostic pipeline (parse + knowledge + LLM) on each case
    - Score:
      - Root cause category match: LLM output matches expected category (exact string match)
      - Evidence quality: ≥50% of cited log lines verified against parsed data
      - Actionability: recommended fix is non-empty and references a concrete action
    - Passing threshold: ≥80% of cases score acceptable on all three dimensions
  Run: `uv run pytest backend/tests/test_llm/ --llm-eval`
  Note: these tests require Ollama running with the configured model. They are slow
    (minutes, not seconds) and run in CI only on tagged releases, not on every push.

Layer 7: Plugin Validation Tests
  Scope: the validation protocol itself works correctly
  Location: backend/tests/test_plugins/
  Fixtures: intentionally broken plugins covering every failure mode:
    - missing_manifest/ — no manifest.json
    - bad_schema/ — manifest with missing required fields
    - crash_on_diagnose/ — plugin whose diagnose() raises an exception
    - timeout_plugin/ — plugin whose diagnose() sleeps beyond the timeout
    - missing_deps/ — plugin declaring a dependency that is not installed
    - permission_violation/ — plugin that attempts a destructive ADB command with read_only permission
    - valid_plugin/ — a correct plugin that passes all stages
  Each fixture has a corresponding expected validation result
  Run: `uv run pytest backend/tests/test_plugins/`
```

### Frontend Testing

```
Unit Tests (Vitest):
  Location: frontend/src/**/*.test.ts
  Scope: Vue component logic, Pinia stores, composables
  Mocking: API calls mocked via msw (Mock Service Worker)
  Coverage target: ≥70% on stores/ and composables/
  Run: `cd frontend && npm run test:unit`

Component Tests (Vitest + Vue Test Utils):
  Scope: component rendering, user interaction, event emission
  Key components to test:
    - DeviceCard: renders device info, emits diagnose/disconnect events
    - DiagnosticReport: renders all sections, handles verified/unverified citations
    - ChatPanel: sends messages, renders streaming responses, maintains scroll
    - LogcatViewer: filters lines, handles selection, triggers explain
    - CommandInput: submits queries, shows confirmation dialog
  Run: `cd frontend && npm run test:component`

E2E Tests (Playwright):
  See Layer 3 above.
  Run: `cd frontend && npx playwright test`
```

### CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: cd backend && uv run ruff check src/ tests/
      - run: cd backend && uv run mypy src/androbugger/

  backend-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: cd backend && uv run pytest tests/ -x --cov=androbugger --cov-report=xml
        # Excludes integration and llm-eval tests (no Ollama in CI for regular pushes)
      - uses: codecov/codecov-action@v4

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run lint

  frontend-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run test:unit -- --coverage

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run build

# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      ollama:
        image: ollama/ollama:latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: ollama pull qwen3:0.6b  # Smallest model for CI
      - run: cd backend && uv run pytest tests/integration/ --integration
      - run: cd backend && uv run pytest tests/test_llm/ --llm-eval

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: cd frontend && npx playwright install && npx playwright test
      - run: docker compose down

  build-containers:
    needs: [integration-tests, e2e-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t androbugger-backend:${{ github.ref_name }} backend/
      - run: docker build -t androbugger-frontend:${{ github.ref_name }} frontend/
      - uses: docker/login-action@v3
      - run: docker push androbugger-backend:${{ github.ref_name }}
      - run: docker push androbugger-frontend:${{ github.ref_name }}

  create-release:
    needs: [build-containers]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
```

### Quality Gates

```
Every pull request must pass:
  - ruff lint (zero errors)
  - mypy type check (zero errors)
  - Backend unit tests (zero failures, ≥80% coverage on changed files)
  - Frontend lint (zero errors)
  - Frontend unit tests (zero failures)
  - Frontend build succeeds

Every tagged release must additionally pass:
  - Backend integration tests
  - LLM evaluation tests (≥80% of cases acceptable)
  - Privacy gate tests (≥95% recall, ≥95% precision)
  - End-to-end Playwright tests
  - Docker image builds successfully
```

## 10. Risk Register

### Technical Risks

```
RISK: Local LLM quality insufficient for complex diagnostic cases
  Likelihood: Medium
  Impact: High — misdiagnoses or unhelpful reports erode user trust
  Mitigation:
    - Deterministic summary always available as baseline (no LLM dependency)
    - Cloud escalation path for hard cases
    - Fine-tuning on accumulated corpus (Phase 4) improves local model over time
    - Evaluation harness catches quality regressions before deployment
  Owner: Backend lead

RISK: Bugreport format changes across Android versions
  Likelihood: High — Google modifies bugreport structure with major Android releases
  Impact: Medium — parsers fail on new format, producing incomplete results
  Mitigation:
    - Parsers use defensive parsing (skip unrecognized sections, never crash)
    - Section splitter uses flexible regex, not hardcoded offsets
    - Parser accuracy tests on bugreports from each supported Android version
    - Plugin system allows rapid deployment of new parsers without core changes
  Owner: Backend lead

RISK: ADB connection instability over wireless
  Likelihood: Medium — wireless ADB drops connections under load or with network congestion
  Impact: Medium — interrupted diagnostics, incomplete bugreports
  Mitigation:
    - Automatic reconnection with exponential backoff
    - Bugreport pull uses retry logic (3 attempts before failing)
    - USB fallback always available
    - Connection health monitoring with status indicators in UI
  Owner: Device layer developer

RISK: LLM hallucination leads to misdiagnosis
  Likelihood: High — all current LLMs hallucinate to some degree
  Impact: High — technician acts on fabricated evidence, wastes repair time
  Mitigation:
    - Citation verifier checks all LLM-referenced log lines against parsed data
    - Unverifiable citations visually flagged in the report
    - Deterministic summary provides ground truth alongside LLM interpretation
    - Confidence level declaration forces model to express uncertainty
    - Users are trained that LLM output is advisory, not authoritative
  Owner: LLM layer developer

RISK: Privacy Gate fails to detect novel PII patterns
  Likelihood: Medium — new apps log unexpected personal data
  Impact: High — personal data sent to cloud LLM provider
  Mitigation:
    - Custom recognizer framework allows rapid addition of new patterns
    - PII test corpus continuously expanded with newly discovered patterns
    - Cloud calls are opt-in by default (no accidental cloud transmission)
    - Audit log captures every cloud-bound prompt for post-hoc review
    - Periodic manual audit of cloud-bound prompts (quarterly)
  Owner: Security lead

RISK: Ollama GPU memory exhaustion with concurrent users
  Likelihood: Medium — multiple simultaneous diagnostic sessions loading 14B model
  Impact: Medium — slow responses or OOM crashes on the inference server
  Mitigation:
    - LiteLLM proxy provides request queuing and concurrency limits
    - Configurable fallback to smaller model (8B) when queue depth exceeds threshold
    - Docker Compose memory limits prevent OOM from affecting other services
    - Monitoring: track GPU memory usage, alert at 90%
  Owner: Infrastructure lead

RISK: Plugin executes malicious or buggy code
  Likelihood: Low (internal team) / Medium (community contributions)
  Impact: High — data corruption, unauthorized device commands, system instability
  Mitigation:
    - Three-stage validation catches most issues before activation
    - Runtime sandbox enforces declared permissions
    - Plugin cannot exceed its declared ADB command tier
    - Network and filesystem access explicitly declared and enforced
    - Execution timeout prevents infinite loops
    - Audit log captures all plugin actions
    - Community plugins require review before listing in marketplace
  Owner: Plugin system developer

RISK: SQLite write contention under concurrent multi-user load
  Likelihood: Medium — SQLite allows only one writer at a time
  Impact: Low-Medium — slow writes, occasional lock timeout errors
  Mitigation:
    - WAL mode enabled (allows concurrent reads during writes)
    - Write operations kept short (no long transactions)
    - Audit log inserts batched where possible
    - If contention becomes measurable: migrate to PostgreSQL (schema is compatible)
    - Monitor: log write lock wait times, alert if p95 exceeds 500ms
  Owner: Backend lead
```

### Organizational Risks

```
RISK: Low user adoption — technicians revert to manual workflows
  Likelihood: Medium
  Impact: High — tool provides no value if nobody uses it
  Mitigation:
    - Involve technicians in UI design and testing from Phase 1
    - First deployment targets the most painful diagnostic cases (the wins that sell themselves)
    - Track adoption metrics: sessions per week, time-to-resolve before vs after
    - Iterate on UI based on direct user feedback
  Owner: Project lead

RISK: Knowledge base cold start — system has no past cases to learn from
  Likelihood: Certain (at launch)
  Impact: Medium — knowledge retrieval provides no value until corpus grows
  Mitigation:
    - Pre-seed with vendor documentation and known-issue bulletins
    - Pre-seed with any existing informal diagnostic notes from the team
    - Deterministic summary and LLM analysis work without knowledge base
    - Knowledge value grows organically with each resolved case
    - Track: cases in knowledge base per month, knowledge retrieval hit rate
  Owner: Project lead

RISK: Key developer leaves — institutional knowledge about the codebase is lost
  Likelihood: Low-Medium
  Impact: High — development stalls if only one person understands the system
  Mitigation:
    - This development plan serves as comprehensive documentation for any new developer
      or LLM coding agent to onboard from
    - Code is open-source and follows standard patterns (FastAPI, Vue 3, SQLite)
    - Automated tests verify behavior: a new developer can refactor with confidence
    - Architecture avoids custom frameworks — every component is a well-documented
      open-source library
  Owner: Project lead

RISK: Open-source project attracts no external contributions
  Likelihood: Medium — niche domain (IFP diagnostics) limits the contributor pool
  Impact: Low — the tool is built for internal use first, community is a bonus
  Mitigation:
    - Plugin system lowers the contribution barrier (no core code changes needed)
    - Reference plugins serve as templates
    - Developer guide is clear and complete
    - The ADB + LLM pattern is generalizable: other Android device fleets can adapt it
  Owner: Project lead
```

## 11. Open-Source Strategy

### License

```
License: Apache License 2.0

Rationale:
  - Permissive: allows internal use, modification, and distribution without copyleft obligations
  - Patent grant: provides explicit patent protection for contributors and users
  - Compatible with all planned dependencies:
    - adbutils: MIT
    - LiteLLM: MIT
    - Presidio: MIT
    - FastAPI: MIT
    - Vue 3: MIT
    - Chroma: Apache 2.0
    - tantivy-py: MIT
    - sentence-transformers: Apache 2.0
  - Allows partners and customers to audit and integrate without legal friction
  - Allows community to fork and adapt for their own device fleets
```

### Repository Structure

```
GitHub Organization: androbugger (or under the company's existing GitHub org)

Repositories:
  androbugger/androbugger          — Main monorepo (backend + frontend + docs)
  androbugger/plugin-template      — GitHub template repo for creating new plugins
  androbugger/plugin-firmware-checker    — Reference plugin
  androbugger/plugin-memory-leak        — Reference plugin
  androbugger/plugin-crash-matcher      — Reference plugin

Main repo branch strategy:
  main          — stable, release-tagged
  develop       — integration branch, CI must pass
  feature/*     — feature branches, PR into develop
  release/vX.Y  — release preparation branches
  hotfix/*      — critical fixes, PR into main and develop
```

### Repository Configuration

```
GitHub Settings:
  - Branch protection on main:
    - Require PR reviews (≥1 approval)
    - Require CI status checks to pass
    - No direct pushes
    - Require linear history (squash merge)
  - Branch protection on develop:
    - Require CI status checks to pass
  - Issue templates:
    - Bug report (device model, firmware, steps to reproduce, logs)
    - Feature request (use case, proposed behavior)
    - Plugin request (what pattern to detect, what fix to apply)
  - PR template:
    - Description of changes
    - Related issue
    - Testing performed
    - Checklist: lint passes, tests pass, docs updated
  - Labels:
    - bug, enhancement, plugin, documentation, security, good-first-issue,
      help-wanted, phase-1, phase-2, phase-3, phase-4
  - GitHub Discussions enabled for community Q&A
```

### Contribution Guidelines

```
File: CONTRIBUTING.md

Sections:
  1. Code of Conduct (Contributor Covenant v2.1)
  2. How to Contribute
     - Report bugs: use the bug report template
     - Suggest features: use the feature request template
     - Submit code: fork → branch → PR into develop
     - Write plugins: use the plugin template repo, follow the developer guide
  3. Development Setup
     - Prerequisites: Linux, Docker, uv, Node.js 20+
     - Clone, install, run: step-by-step commands
     - Run tests: backend and frontend commands
  4. Code Style
     - Python: ruff with default rules, mypy strict mode
     - TypeScript: ESLint + Prettier with Vue plugin
     - Commit messages: Conventional Commits (feat:, fix:, docs:, chore:, test:)
  5. Pull Request Process
     - One feature per PR
     - All CI checks must pass
     - At least one review approval
     - Squash merge into develop
  6. Plugin Contributions
     - Must pass the three-stage validation protocol
     - Must include test fixtures
     - Must include README with usage instructions
     - License must be Apache 2.0 or MIT compatible
  7. Security Vulnerability Reporting
     - Email security@<company>.com (do not open a public issue)
     - Response within 48 hours
     - Coordinated disclosure after fix is available
```

### Documentation

```
Location: docs/ in main repo + GitHub Wiki for community content

docs/
├── whitepaper.md                  — Project vision and architecture (this companion document)
├── development-plan.md            — This document
├── plugin-developer-guide.md      — How to create plugins (Phase 2 deliverable)
├── fine-tuning-guide.md           — How to fine-tune a local model (Phase 4 deliverable)
├── mcp-integration.md             — How to connect Androbugger to AI assistants (Phase 4)
├── api-reference.md               — REST + WebSocket API documentation (auto-generated from
│                                    FastAPI OpenAPI schema + manual annotations)
├── deployment-guide.md            — Docker Compose setup, Ollama configuration, Caddy setup,
│                                    hardware requirements, network configuration
├── user-guide.md                  — End-user documentation for technicians and QA engineers
└── admin-guide.md                 — Administrator documentation: user management, LLM config,
                                     plugin management, audit, encryption, budgets

API reference auto-generation:
  - FastAPI produces OpenAPI 3.1 schema at /api/docs (Swagger UI) and /api/redoc (ReDoc)
  - Export schema to docs/api-reference.md using a build script
  - Run on every release tag
```

### Release Process

```
Versioning: Semantic Versioning (semver)
  - MAJOR: breaking changes to API, plugin manifest schema, or database schema
  - MINOR: new features, new plugin capabilities, backward-compatible API additions
  - PATCH: bug fixes, security patches, dependency updates

Release cadence:
  - Phase 1-3: release at end of each phase (v0.1.0, v0.2.0, v0.3.0)
  - Phase 4+: monthly minor releases, patch releases as needed
  - Security fixes: released within 72 hours of confirmed vulnerability

Release checklist:
  1. All CI checks pass on develop
  2. Release branch created: release/vX.Y.Z
  3. Version bumped in pyproject.toml, package.json, docker-compose.yml
  4. CHANGELOG.md updated with release notes
  5. Integration tests and LLM eval tests pass
  6. E2E tests pass
  7. PR from release branch to main, approved and merged
  8. Tag created: vX.Y.Z
  9. GitHub Release created with auto-generated notes + manual summary
  10. Docker images built and pushed with version tag
  11. Announce in GitHub Discussions
```

### Hardware Requirements (for documentation)

```
Minimum (local model: Qwen3 8B Q4):
  - CPU: 4 cores
  - RAM: 16 GB
  - GPU: 6 GB VRAM (NVIDIA with CUDA) or CPU-only inference (slower, ~5 tok/s)
  - Storage: 50 GB (OS + models + diagnostic data)
  - OS: Ubuntu 22.04+ or Debian 12+

Recommended (local model: Qwen3 14B Q4):
  - CPU: 8 cores
  - RAM: 32 GB
  - GPU: 12+ GB VRAM (NVIDIA RTX 3060 or better)
  - Storage: 100 GB SSD
  - OS: Ubuntu 22.04+ or Debian 12+

Cloud-only mode (no local LLM, all inference via cloud APIs):
  - CPU: 2 cores
  - RAM: 8 GB
  - GPU: not required
  - Storage: 30 GB
  - OS: Ubuntu 22.04+ or Debian 12+
  - Network: outbound HTTPS to cloud provider APIs
```
