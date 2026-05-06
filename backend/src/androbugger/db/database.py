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
