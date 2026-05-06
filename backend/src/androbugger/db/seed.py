"""Seed default data into a fresh database."""
import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher

from androbugger.db.database import get_db


async def seed_defaults() -> None:
    ph = PasswordHasher()
    async with get_db() as db:
        # Default admin user
        row = await (await db.execute("SELECT id FROM users WHERE username='admin'")).fetchone()
        if not row:
            await db.execute(
                """INSERT INTO users (id, username, password_hash, role, force_password_change, created_at)
                   VALUES (?, 'admin', ?, 'admin', TRUE, ?)""",
                (str(uuid.uuid4()), ph.hash("admin"), datetime.now(timezone.utc).isoformat()),
            )

        # Default LLM provider (Ollama)
        row = await (await db.execute("SELECT id FROM llm_providers WHERE is_default=TRUE")).fetchone()
        if not row:
            await db.execute(
                """INSERT INTO llm_providers (id, provider_type, model_name, endpoint_url,
                   is_local, is_default, is_enabled, priority, max_tokens)
                   VALUES (?, 'ollama', 'qwen3:14b', 'http://ollama:11434', TRUE, TRUE, TRUE, 10, 4096)""",
                (str(uuid.uuid4()),),
            )

        # Default command permission tiers
        default_perms = [
            ("logcat*", "read_only", "technician", False, "Read logcat output"),
            ("dumpsys*", "read_only", "technician", False, "Read dumpsys output"),
            ("getprop*", "read_only", "technician", False, "Read device properties"),
            ("ps*", "read_only", "technician", False, "List processes"),
            ("top*", "read_only", "technician", False, "Show process stats"),
            ("df*", "read_only", "technician", False, "Show disk usage"),
            ("cat /proc/*", "read_only", "technician", False, "Read proc filesystem"),
            ("wm *", "read_only", "technician", False, "Window manager query"),
            ("screencap*", "read_only", "technician", False, "Capture screen"),
            ("pm clear*", "state_changing", "technician", True, "Clear app data"),
            ("pm install*", "state_changing", "developer", True, "Install APK"),
            ("am force-stop*", "state_changing", "technician", True, "Force stop app"),
            ("am start*", "state_changing", "technician", True, "Start activity"),
            ("settings put*", "state_changing", "developer", True, "Change settings"),
            ("svc *", "state_changing", "developer", True, "System service control"),
            ("reboot*", "destructive", "developer", True, "Reboot device"),
            ("wipe*", "destructive", "admin", True, "Wipe device data"),
            ("recovery*", "destructive", "admin", True, "Enter recovery mode"),
        ]
        for pattern, tier, min_role, requires_confirmation, description in default_perms:
            await db.execute(
                """INSERT OR IGNORE INTO command_permissions
                   (pattern, tier, min_role, requires_confirmation, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (pattern, tier, min_role, requires_confirmation, description),
            )

        await db.commit()
