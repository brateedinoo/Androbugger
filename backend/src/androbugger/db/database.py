import aiosqlite
from contextlib import asynccontextmanager
from androbugger.config import settings


_db_path = str(settings.db_path)


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await _run_migrations(db)
        await db.commit()


async def _run_migrations(db: aiosqlite.Connection) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
    )
    row = await (await db.execute("SELECT MAX(version) FROM schema_version")).fetchone()
    current = row[0] or 0

    migrations = _get_migrations()
    for version, sql in migrations:
        if version > current:
            await db.executescript(sql)
            await db.execute("INSERT INTO schema_version VALUES (?)", (version,))

    await db.commit()


def _get_migrations() -> list[tuple[int, str]]:
    return [
        (1, _MIGRATION_001),
        (2, _MIGRATION_002),
        (3, _MIGRATION_003),
        (4, _MIGRATION_004),
    ]


_MIGRATION_001 = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('technician', 'qa_engineer', 'developer', 'admin')),
    force_password_change BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    serial TEXT PRIMARY KEY,
    model TEXT,
    firmware_version TEXT,
    connection_type TEXT CHECK (connection_type IN ('usb', 'tcp')),
    ip_address TEXT,
    connected_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diagnostic_sessions (
    id TEXT PRIMARY KEY,
    device_serial TEXT NOT NULL,
    device_model TEXT,
    firmware_version TEXT,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'resolved', 'failed')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    bugreport_path TEXT,
    parsed_data_path TEXT,
    deterministic_summary TEXT,
    llm_report TEXT,
    llm_provider TEXT,
    llm_token_count INTEGER,
    llm_cost_estimate REAL,
    root_cause TEXT,
    applied_fix TEXT,
    resolution_notes TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES diagnostic_sessions(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    llm_provider TEXT,
    token_count INTEGER
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    device_serial TEXT,
    detail TEXT,
    ip_address TEXT
);

CREATE TABLE IF NOT EXISTS plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    author TEXT,
    description TEXT,
    manifest_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'quarantined', 'validating')),
    loaded_at TEXT,
    validation_result TEXT,
    permissions TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL CHECK (namespace IN ('vendor_docs', 'past_diagnoses', 'aosp_reference')),
    title TEXT NOT NULL,
    source TEXT,
    device_model TEXT,
    firmware_version TEXT,
    content_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS llm_providers (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    model_name TEXT NOT NULL,
    endpoint_url TEXT,
    is_local BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    max_tokens INTEGER DEFAULT 4096,
    budget_limit_usd REAL,
    budget_spent_usd REAL DEFAULT 0.0,
    budget_reset_interval TEXT
);

CREATE TABLE IF NOT EXISTS batch_diagnostics (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    device_serials TEXT NOT NULL,
    session_ids TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS command_permissions (
    pattern TEXT PRIMARY KEY,
    tier TEXT NOT NULL CHECK (tier IN ('read_only', 'state_changing', 'destructive')),
    min_role TEXT NOT NULL CHECK (min_role IN ('technician', 'qa_engineer', 'developer', 'admin')),
    requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT
);
"""

_MIGRATION_002 = """
CREATE VIRTUAL TABLE IF NOT EXISTS diagnostic_search USING fts5(
    session_id,
    llm_report,
    deterministic_summary,
    root_cause,
    applied_fix,
    resolution_notes,
    content='diagnostic_sessions',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS diagnostic_sessions_ai
AFTER INSERT ON diagnostic_sessions BEGIN
    INSERT INTO diagnostic_search(rowid, session_id, llm_report, deterministic_summary,
        root_cause, applied_fix, resolution_notes)
    VALUES (new.rowid, new.id, new.llm_report, new.deterministic_summary,
        new.root_cause, new.applied_fix, new.resolution_notes);
END;

CREATE TRIGGER IF NOT EXISTS diagnostic_sessions_au
AFTER UPDATE ON diagnostic_sessions BEGIN
    INSERT INTO diagnostic_search(diagnostic_search, rowid, session_id, llm_report,
        deterministic_summary, root_cause, applied_fix, resolution_notes)
    VALUES ('delete', old.rowid, old.id, old.llm_report, old.deterministic_summary,
        old.root_cause, old.applied_fix, old.resolution_notes);
    INSERT INTO diagnostic_search(rowid, session_id, llm_report, deterministic_summary,
        root_cause, applied_fix, resolution_notes)
    VALUES (new.rowid, new.id, new.llm_report, new.deterministic_summary,
        new.root_cause, new.applied_fix, new.resolution_notes);
END;
"""

_MIGRATION_003 = """
CREATE TABLE IF NOT EXISTS device_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    color TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_group_members (
    group_id TEXT NOT NULL REFERENCES device_groups(id) ON DELETE CASCADE,
    device_serial TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (group_id, device_serial)
);

CREATE TABLE IF NOT EXISTS scheduled_diagnostics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    device_serial TEXT,
    group_id TEXT REFERENCES device_groups(id),
    cron_expr TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    template_id TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    last_session_id TEXT REFERENCES diagnostic_sessions(id),
    next_run_at TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN (
        'session_complete','session_failed','regression_detected',
        'scheduled_run','hardware_alert','plugin_error'
    )),
    title TEXT NOT NULL,
    body TEXT,
    session_id TEXT,
    device_serial TEXT,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read, created_at DESC);

CREATE TABLE IF NOT EXISTS hardware_checks (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES diagnostic_sessions(id),
    device_serial TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    overall_status TEXT NOT NULL CHECK (overall_status IN ('pass','warning','fail')),
    results_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finetune_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exported_at TEXT NOT NULL,
    exported_by TEXT NOT NULL REFERENCES users(id),
    record_count INTEGER NOT NULL,
    output_path TEXT NOT NULL,
    filters_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, timestamp DESC);
"""

_MIGRATION_004 = """
-- Rebuild knowledge_entries to extend namespace CHECK and add community columns.
-- SQLite cannot ALTER column constraints so we rename+recreate.
CREATE TABLE IF NOT EXISTS knowledge_entries_v2 (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL CHECK (namespace IN (
        'vendor_docs', 'past_diagnoses', 'aosp_reference', 'manual')),
    title TEXT NOT NULL,
    source TEXT,
    device_model TEXT,
    firmware_version TEXT,
    content_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    metadata TEXT,
    helpful_votes INTEGER NOT NULL DEFAULT 0,
    unhelpful_votes INTEGER NOT NULL DEFAULT 0,
    author_id TEXT REFERENCES users(id),
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TEXT
);
INSERT OR IGNORE INTO knowledge_entries_v2
    SELECT id, namespace, title, source, device_model, firmware_version,
           content_hash, indexed_at, metadata, 0, 0, NULL, FALSE, NULL
    FROM knowledge_entries;
DROP TABLE knowledge_entries;
ALTER TABLE knowledge_entries_v2 RENAME TO knowledge_entries;

-- Knowledge feedback (one vote per user per entry)
CREATE TABLE IF NOT EXISTS knowledge_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    helpful BOOLEAN NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(entry_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_feedback_entry ON knowledge_feedback(entry_id);

-- Outbound webhook endpoints
CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    secret TEXT NOT NULL DEFAULT '',
    events TEXT NOT NULL DEFAULT '[]',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

-- Webhook delivery log
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id TEXT NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    response_status INTEGER,
    delivered_at TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint
    ON webhook_deliveries(endpoint_id, delivered_at DESC);

-- Per-plugin runtime config overrides
CREATE TABLE IF NOT EXISTS plugin_configs (
    plugin_id TEXT PRIMARY KEY,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL
);

-- Data retention policies
CREATE TABLE IF NOT EXISTS retention_policies (
    entity TEXT PRIMARY KEY
        CHECK (entity IN (
            'diagnostic_sessions','audit_log','webhook_deliveries','notifications')),
    max_age_days INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL
);
"""
