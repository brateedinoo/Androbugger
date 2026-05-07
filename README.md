# Androbugger

**LLM-powered diagnostic platform for Android-based Interactive Flat Panels (IFPs).**

Connect a returned or faulty ADVANTouch IFP, start a diagnostic session, and receive an
actionable report — root cause, applied fix recommendation, and referenced evidence from the
device's own logs — typically in under 5 minutes.

---

## Table of Contents

- [What it does](#what-it-does)
- [Quick Start — Docker (recommended)](#quick-start--docker-recommended)
- [Development Setup](#development-setup)
- [Configuration Reference](#configuration-reference)
- [Roles and Permissions](#roles-and-permissions)
- [Feature Guide](#feature-guide)
- [Plugin Development](#plugin-development)
- [MCP Integration](#mcp-integration)
- [Architecture](#architecture)
- [API Reference](#api-reference)

---

## What it does

Androbugger automates the most time-consuming part of device repair triage: reading through
thousands of lines of Android system logs, cross-referencing them with known failure patterns,
and writing a coherent diagnosis. It does this by:

1. Pulling a full bugreport from the connected device over ADB
2. Parsing it deterministically (ANR traces, tombstones, logcat, dmesg, dumpsys, thermal, memory)
3. Retrieving relevant past diagnoses and vendor docs from a local hybrid vector/keyword index
4. Sending the structured summary to a local Ollama LLM (or a cloud fallback)
5. Verifying that every claim in the LLM output is backed by evidence in the parsed data
6. Storing the report, indexing it for future retrieval, and dispatching webhook events

All PII (emails, IPs, serial numbers) is stripped before any cloud LLM call. Data stays on-premise
by default.

---

## Quick Start — Docker (recommended)

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- The host machine must have `udev` rules or equivalent so the backend container can see USB
  devices. On most Linux hosts this works automatically with the `privileged: true` setting in
  `docker-compose.yml`.
- ~10 GB of free disk space for the default Ollama models.

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/brateedinoo/androbugger.git
cd androbugger

# 2. Create your environment file
cp .env.example .env
```

Open `.env` and set at minimum:

```env
SECRET_KEY=<long-random-string>   # used to sign JWT tokens — keep this secret
```

```bash
# 3. Build and start all services
docker compose up -d

# 4. Download the LLM models (one-time, ~8 GB total)
docker compose exec ollama ollama pull qwen3:14b
docker compose exec ollama ollama pull nomic-embed-text

# 5. Check everything is healthy
docker compose ps
```

Open **http://localhost** in your browser.

Log in with **admin / admin**. You will immediately be prompted to set a new password — do so
before doing anything else.

### Connecting a device

Plug the IFP into the host machine via USB. ADB debugging must be enabled on the device:

1. On the IFP: *Settings → About → tap Build Number 7 times → Developer Options → enable USB Debugging*
2. Accept the RSA fingerprint prompt that appears on the device screen
3. The device appears automatically in the Androbugger device list within a few seconds

For **wireless ADB** (TCP/IP mode):

```bash
# From the host (device must already be connected via USB first)
adb tcpip 5555
adb connect <device-ip>:5555
```

Then enter the device IP and port in Androbugger's "Connect TCP" dialog.

### Updating

```bash
git pull
docker compose build
docker compose up -d
```

Database migrations run automatically on startup.

---

## Development Setup

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 22+
- A running Ollama instance (local or remote)
- A running Redis instance (only needed for background job features; most dev workflows work without it)

### Backend

```bash
cd backend

# Install all dependencies including dev tools
uv sync --dev

# Run the development server (auto-reloads on file changes)
uv run uvicorn androbugger.main:app --reload --port 8000
```

The backend starts at **http://localhost:8000**. Interactive API docs are at
http://localhost:8000/docs (Swagger) and http://localhost:8000/redoc.

The SQLite database and data directories are created automatically under `/data/androbugger/`.
To use a local path during development, set the env var:

```bash
export ANDROBUGGER_DATA_DIR=$HOME/.androbugger
export ANDROBUGGER_DB_PATH=$HOME/.androbugger/androbugger.db
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server (hot-reload, proxies /api and /ws to localhost:8000)
npm run dev
```

The frontend starts at **http://localhost:5173**.

### Running tests

```bash
cd backend

# Run all tests (skip hardware device tests which need a real ADB device)
uv run pytest tests/ -q --ignore=tests/test_device

# Run a specific test file
uv run pytest tests/test_api/test_diagnostics.py -v

# Run lint check
uv run ruff check src/
```

---

## Configuration Reference

All settings are read from environment variables prefixed with `ANDROBUGGER_`, or from a `.env`
file in the project root. In Docker, set them under the `environment:` key in `docker-compose.yml`
or override with a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `ANDROBUGGER_SECRET_KEY` | `change-me-in-production-...` | **Required in production.** JWT signing key. Use a random 64-char string. |
| `ANDROBUGGER_DEFAULT_LLM_MODEL` | `ollama/qwen3:14b` | Primary LLM. Use `ollama/<model>` for local, `anthropic/claude-...` for cloud. |
| `ANDROBUGGER_FALLBACK_LLM_MODEL` | `ollama/qwen3:8b` | Used when primary fails or is unavailable. |
| `ANDROBUGGER_OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama API endpoint. |
| `ANDROBUGGER_REDIS_URL` | `redis://redis:6379` | Redis for background job queues. |
| `ANDROBUGGER_DB_PATH` | `/data/androbugger/androbugger.db` | SQLite database file path. |
| `ANDROBUGGER_DATA_DIR` | `/data/androbugger` | Root for bugreports, parsed output, ChromaDB, Tantivy indexes. |
| `ANDROBUGGER_ENABLE_PRIVACY_GATE` | `true` | Strip PII before cloud LLM calls. Disable only for local-only deployments. |
| `ANDROBUGGER_ACCESS_TOKEN_EXPIRE_HOURS` | `8` | JWT access token lifetime. |
| `ANDROBUGGER_MCP_API_KEY` | *(empty)* | API key for the MCP server endpoint. Set to enable Claude Desktop integration. |
| `ANDROBUGGER_SMTP_HOST` | *(empty)* | SMTP server for email digests. Leave empty to disable email. |
| `ANDROBUGGER_SMTP_PORT` | `587` | SMTP port. |
| `ANDROBUGGER_SMTP_USERNAME` | *(empty)* | SMTP auth username. |
| `ANDROBUGGER_SMTP_PASSWORD` | *(empty)* | SMTP auth password. |
| `ANDROBUGGER_SMTP_FROM` | `androbugger@localhost` | Sender address for outbound emails. |
| `ANDROBUGGER_WEBHOOK_RETRY_ATTEMPTS` | `3` | Max delivery attempts per webhook event. |
| `ANDROBUGGER_AUDIT_RETENTION_DAYS` | `90` | Days to keep audit log entries (overridden by Admin → System → Retention). |
| `ANDROBUGGER_ADB_DEVICE_POLL_INTERVAL` | `5.0` | Seconds between ADB device list refreshes. |

### Using a cloud LLM

To use Anthropic Claude instead of (or in addition to) Ollama:

```env
ANDROBUGGER_DEFAULT_LLM_MODEL=anthropic/claude-sonnet-4-6
ANDROBUGGER_FALLBACK_LLM_MODEL=ollama/qwen3:8b
```

LiteLLM reads provider API keys from standard env vars:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # if using OpenAI models
```

The privacy gate always strips PII before the text leaves the local machine, regardless of which
provider is configured.

### GPU acceleration for Ollama

Uncomment the `deploy:` block in `docker-compose.yml`:

```yaml
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Then rebuild: `docker compose up -d --build ollama`.

---

## Roles and Permissions

Androbugger has four roles assigned per user. A user can only hold one role at a time.

| Role | Who it's for | Key capabilities |
|---|---|---|
| `technician` | Repair bench staff | View device list, run diagnostics, read reports, chat on sessions, vote on knowledge entries, run read-only ADB commands |
| `qa_engineer` | QA / test engineers | Same as technician |
| `developer` | Senior engineers | All technician capabilities + create/edit knowledge entries, access Analytics dashboard, export fine-tuning data, manage plugins |
| `admin` | IT / platform owners | Full access: user management, webhook configuration, system health, data retention policies, destructive ADB commands |

### ADB command tiers

Commands run through the ADB Command Runner are gated by tier:

| Tier | Examples | Min role | Requires confirmation |
|---|---|---|---|
| `read_only` | `logcat`, `dumpsys`, `getprop`, `ps`, `df` | technician | No |
| `state_changing` | `pm clear`, `am force-stop`, `am start`, `settings put` | technician / developer | Yes |
| `destructive` | `reboot`, `wipe`, `recovery` | developer / admin | Yes |

Admins can customise these tiers per command pattern from the Admin panel.

---

## Feature Guide

### Running a diagnostic

1. Go to **Devices** — your connected device should appear automatically.
2. Click **Diagnose** on the device card.
3. Optionally select a diagnostic template (Standard / Performance Focus / Crash Investigation / Network).
4. Wait for the report. Status updates appear in real time. Typical time: 2–5 minutes.
5. The report shows:
   - Severity badge (info / warning / error / critical)
   - Deterministic summary (ANR count, tombstone count, OOM events, thermal events, crash loops)
   - LLM narrative report with root cause and applied fix recommendation
   - Evidence citations — every LLM claim is traced back to a specific log entry
   - Chat panel — ask follow-up questions about the session

### Knowledge base

The knowledge base is a hybrid vector + keyword index that the LLM consults during every
diagnostic to retrieve relevant past cases, vendor docs, and AOSP reference material.

**Namespaces:**

| Namespace | Source | Populated by |
|---|---|---|
| `past_diagnoses` | Resolved diagnostic sessions | Automatic — indexed when a session is marked resolved |
| `vendor_docs` | ADVANTouch / Android vendor documentation | Admin file upload or manual entry |
| `aosp_reference` | AOSP error patterns and known issues | Admin file upload or manual entry |
| `manual` | Community knowledge contributed by developers | Manual entry via Knowledge → Add Entry |

To add a manual entry: go to **Knowledge**, click **Add Entry**, enter a title and the full
content in the text area. The entry is immediately indexed and will appear in future diagnostic
retrievals.

Technicians and above can vote entries helpful or unhelpful using the thumbs-up/down buttons.
Vote counts are visible to all users and help surface the most useful entries.

### Analytics dashboard

Available to developers and admins at **/analytics**.

- **Overview cards**: total sessions, resolved %, average time-to-resolution, top failure pattern
- **Daily trend chart**: sessions per day with failure rate overlay (configurable 7 / 30 / 90 days)
- **Failure patterns table**: root causes with occurrence count, affected device count, link to an example session
- **Top root causes bar chart**: relative frequency of the 5 most common root causes

### Scheduled diagnostics

Create recurring diagnostic jobs that run automatically at a cron schedule. Go to
**Scheduled** → **New Schedule**. You can target a single device serial or an entire device group.

The scheduler checks every 60 seconds and fires any due jobs. Results appear as normal diagnostic
sessions and trigger webhook events if configured.

### Device groups

Group devices logically (e.g. by location, model line, or customer) in **Devices → Groups**.
Groups are used as targets for scheduled diagnostics and can be used to filter analytics.

### Webhooks

Push diagnostic events to external systems (Slack, PagerDuty, ticketing systems, RMA workflows).

Go to **Admin → Integrations → Add Webhook**:

1. Enter a name, target URL, and an optional HMAC secret for signature verification.
2. Select which events to subscribe to:
   - `session.completed` — diagnostic finished successfully
   - `session.failed` — diagnostic failed
   - `hardware.alert` — hardware check detected a problem
   - `regression.detected` — a device regression pattern was identified
   - `plugin.error` — a plugin raised an unhandled exception
3. Click **Test** to send a test payload immediately and see the HTTP response.

Every delivery is logged under **Deliveries**. Failed deliveries are retried up to
`ANDROBUGGER_WEBHOOK_RETRY_ATTEMPTS` times with exponential back-off.

**Verifying the signature** (receiver side):

```python
import hashlib, hmac
expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
assert request.headers["X-Androbugger-Signature"] == f"sha256={expected}"
```

### Notifications

In-app notifications appear in the bell icon in the nav bar. Notifications are generated for:

- Session completed / failed
- Scheduled job run
- Hardware alert
- Regression detected
- Plugin error

### Screen mirroring

Click **Mirror** on a device card to stream the device screen in real time over WebSocket.
Requires `scrcpy-server` to be available on the device or sideloaded.

### System health and data retention

Available to admins at **Admin → System**.

- **Health**: current DB file size, session count, knowledge entry count, active scheduled jobs, next scheduled run
- **Retention policies**: configure max age (in days) for each data category. Click **Run Now** to purge immediately. The purge also runs automatically once per day.

| Entity | Default retention |
|---|---|
| `diagnostic_sessions` | 365 days |
| `audit_log` | 180 days |
| `webhook_deliveries` | 30 days |
| `notifications` | 90 days |

---

## Plugin Development

Plugins extend the diagnostic engine with custom pattern matchers, pre-processors, and
post-processors. See [docs/plugin-developer-guide.md](docs/plugin-developer-guide.md) for the
complete API.

**Quick start:**

```
plugins/
└── my_plugin/
    ├── manifest.json      # required: id, name, version, author, capabilities
    ├── plugin.py          # required: class MyPlugin(Plugin)
    └── tests/
        ├── input.json     # sample parsed bugreport
        └── expected.json  # expected plugin output
```

Plugins are hot-loaded from the `plugins/` directory. Drop a new folder in and Androbugger picks
it up within seconds (inotify watch). Invalid or failing plugins are quarantined and reported in
Admin → Plugins — they do not crash the main process.

Admins can override plugin runtime config (any key defined in `manifest.json` under `metadata`)
via **Admin → Plugins → {plugin} → Configure** without touching the plugin source.

To update a plugin from its git remote: click **Update** on the plugin card. Androbugger runs
`git pull` in the plugin directory and reloads it automatically.

---

## MCP Integration

Androbugger exposes an MCP (Model Context Protocol) server that lets Claude Desktop — or any
MCP-compatible client — query diagnostic sessions, search the knowledge base, and run diagnostics
without opening the web UI.

**Enable the MCP server:**

```env
ANDROBUGGER_MCP_API_KEY=<choose-a-strong-key>
```

**Claude Desktop config** (`~/.config/claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "androbugger": {
      "command": "uvx",
      "args": ["androbugger-mcp"],
      "env": {
        "ANDROBUGGER_API_URL": "http://localhost:8000",
        "ANDROBUGGER_MCP_API_KEY": "<your-key>"
      }
    }
  }
}
```

See [docs/mcp-integration.md](docs/mcp-integration.md) for all available tools.

---

## Architecture

```
Browser (Vue 3 + PrimeVue + Pinia)
  │  REST (HTTPS) + WebSocket (wss://)
  ▼
Caddy  ──────────────────── reverse proxy (ports 80 / 443)
  │
  ├─► FastAPI backend (port 8000)
  │     ├── Auth layer         (JWT, argon2 password hashing, RBAC)
  │     ├── Device layer       (adbutils, USB + TCP/IP ADB, WebSocket status broadcast)
  │     ├── Diagnostic engine  (bugreport pull → parse → LLM → verify → store)
  │     │     ├── Parser layer (bugreport, logcat, ANR, tombstone, dmesg, dumpsys, thermal, HW)
  │     │     ├── LLM layer    (LiteLLM → Ollama local / cloud providers)
  │     │     ├── Privacy gate (Presidio — strips PII before any cloud LLM call)
  │     │     └── Verifier     (citation check — each LLM claim traced to parsed evidence)
  │     ├── Knowledge layer    (ChromaDB vectors + Tantivy BM25 hybrid search)
  │     ├── Plugin system      (inotify-watched directory, 3-stage validation, sandbox)
  │     ├── Analytics          (SQL aggregations over diagnostic_sessions)
  │     ├── Webhooks           (outbound HTTP, HMAC signatures, retry)
  │     ├── Scheduler          (croniter-based, per-device and per-group)
  │     ├── MCP server         (Model Context Protocol for Claude Desktop)
  │     └── Fine-tuning        (export JSONL training data, ROUGE-L evaluation)
  │
  ├─► Ollama  (local LLM inference, port 11434)
  ├─► Redis   (arq job queue for background tasks)
  └─► SQLite  (primary database, WAL mode, 4 migrations)
```

### Data storage layout

```
/data/androbugger/
  androbugger.db        ← SQLite (users, sessions, knowledge, webhooks, audit log, ...)
  bugreports/           ← raw bugreport zips pulled from devices
  parsed/               ← JSON parsed output per session
  chroma/               ← ChromaDB vector store (knowledge embeddings)
  tantivy/              ← Tantivy full-text index (knowledge BM25)
```

### Database schema (key tables)

| Table | Purpose |
|---|---|
| `users` | Accounts with roles and argon2 password hashes |
| `diagnostic_sessions` | One row per diagnostic run, including LLM report and root cause |
| `chat_messages` | Follow-up chat history per session |
| `knowledge_entries` | Knowledge base documents (all namespaces) |
| `knowledge_feedback` | Per-user thumbs-up / thumbs-down votes |
| `webhook_endpoints` | Configured outbound webhook targets |
| `webhook_deliveries` | Delivery log per event (status, retries, error) |
| `device_groups` | Named device collections |
| `scheduled_diagnostics` | Cron-scheduled diagnostic jobs |
| `notifications` | In-app notifications per user |
| `hardware_checks` | Results from hardware diagnostic runs |
| `plugin_configs` | Runtime config overrides per plugin |
| `retention_policies` | Configurable data-retention ages |
| `audit_log` | Immutable record of every significant action |
| `command_permissions` | ADB command tier/role rules |
| `llm_providers` | Configured LLM providers with priority |

---

## API Reference

The full interactive API reference is available at http://localhost/docs when the server is running.

Key endpoint groups:

| Prefix | Description |
|---|---|
| `/api/auth` | Login, logout, token refresh, password change |
| `/api/devices` | List devices, connect/disconnect, WebSocket status stream |
| `/api/diagnostics` | Create sessions, poll status, get report, resolve, export PDF |
| `/api/knowledge` | Search, list entries, CRUD, feedback votes |
| `/api/analytics` | Overview stats, trends, failure patterns, device health, regression map |
| `/api/webhooks` | CRUD webhook endpoints, delivery history, test delivery |
| `/api/commands` | Run ADB commands (natural language or direct), get permission tier |
| `/api/plugins` | List plugins, install from URL, configure, update |
| `/api/scheduled-diagnostics` | CRUD scheduled jobs |
| `/api/device-groups` | CRUD device groups and membership |
| `/api/notifications` | List, mark read, delete notifications |
| `/api/system` | Health metrics, retention policies, run purge |
| `/api/admin` | User management, LLM provider config, command permissions |
| `/ws/logcat/{serial}` | Real-time logcat stream (WebSocket) |
| `/ws/mirror/{serial}` | Real-time screen mirror stream (WebSocket) |
| `/ws/devices` | Device connect/disconnect events (WebSocket) |

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `admin` | admin |

The admin account has `force_password_change = true` — you will be redirected to change the
password on first login and cannot use the application until you do.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
