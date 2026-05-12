"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from androbugger.api import (
    admin,
    analytics,
    auth,
    chat,
    commands,
    devices,
    diagnostics,
    groups,
    knowledge,
    logcat,
    mirror,
    notifications,
    scheduled_diagnostics,
    system,
    webhooks,
)
from androbugger.api import (
    plugins as plugins_api,
)
from androbugger.config import settings
from androbugger.db.database import init_db
from androbugger.db.seed import seed_defaults
from androbugger.device import adb as adb_module
from androbugger.device import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data dirs exist
    settings.bugreport_dir.mkdir(parents=True, exist_ok=True)
    settings.parsed_dir.mkdir(parents=True, exist_ok=True)

    # Init DB
    await init_db()
    await seed_defaults()
    logger.info("Database initialised")

    # Load permission tiers and provider endpoint cache from DB
    from androbugger.db.database import get_db
    from androbugger.llm import router as llm_router
    async with get_db() as db:
        rows = await (await db.execute("SELECT * FROM command_permissions")).fetchall()
        adb_module.load_permission_tiers([dict(r) for r in rows])
        provider_rows = await (await db.execute("SELECT * FROM llm_providers")).fetchall()
        llm_router.refresh_provider_cache([dict(r) for r in provider_rows])

    # ADB server pre-flight — surfaces USB/daemon issues in startup logs
    try:
        proc = await asyncio.create_subprocess_exec(
            "adb", "start-server",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10.0)
        logger.info("ADB server started (exit %s)", proc.returncode)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("adb start-server timed out after 10s")
    except FileNotFoundError:
        logger.warning("adb binary not found — USB device features unavailable")

    # Load plugins
    from androbugger.plugins.loader import load_all_plugins
    plugins_dir = Path(__file__).parent.parent.parent.parent.parent / "plugins"
    load_all_plugins(plugins_dir)

    # Register device status broadcast callback
    manager.add_status_callback(devices.broadcast_device_event)

    # Start background device polling
    poll_task = asyncio.create_task(manager.poll_devices())
    logger.info("Device polling started")

    # Start cron-based scheduler loop
    sched_task = asyncio.create_task(_run_scheduler_loop())
    logger.info("Scheduler loop started")

    # Start daily data-retention task
    retention_task = asyncio.create_task(_run_daily_retention())
    logger.info("Retention loop started")

    yield

    poll_task.cancel()
    sched_task.cancel()
    retention_task.cancel()
    for t in (poll_task, sched_task, retention_task):
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete")


app = FastAPI(
    title="Androbugger",
    version="0.1.0",
    description="LLM-powered diagnostic platform for Android IFPs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(diagnostics.router)
app.include_router(commands.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(plugins_api.router)
app.include_router(admin.router)
app.include_router(groups.router)
app.include_router(notifications.router)
app.include_router(scheduled_diagnostics.router)
app.include_router(analytics.router)
app.include_router(webhooks.router)
app.include_router(system.router)

# WebSocket routes
app.include_router(logcat.router)
app.include_router(mirror.router)

# WebSocket route for device status (prefix-less — registered in devices.py)
# Note: /ws/devices is handled inside devices.py but needs mounting at app level
app.add_api_websocket_route("/ws/devices", devices.ws_devices)


async def _run_scheduler_loop() -> None:
    """Check enabled schedules every 60s and fire any that are due."""
    while True:
        try:
            await asyncio.sleep(60)
            await _tick_schedules()
        except asyncio.CancelledError:
            break
        except Exception:
            pass


async def _tick_schedules() -> None:
    from androbugger.db.database import get_db
    from androbugger.scheduling.scheduler import run_scheduled_diagnostic

    now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id FROM scheduled_diagnostics WHERE enabled=TRUE AND next_run_at <= ?",
            (now_iso,),
        )).fetchall()

    for row in rows:
        schedule_id = row["id"]
        try:
            await run_scheduled_diagnostic({}, schedule_id)
            # Update next_run_at
            async with get_db() as db:
                sched_row = await (await db.execute(
                    "SELECT cron_expr FROM scheduled_diagnostics WHERE id=?", (schedule_id,)
                )).fetchone()
                if sched_row:
                    from datetime import datetime

                    from croniter import croniter
                    c = croniter(sched_row["cron_expr"], datetime.now(UTC))
                    next_run = c.get_next(datetime).isoformat()
                    await db.execute(
                        "UPDATE scheduled_diagnostics SET next_run_at=? WHERE id=?",
                        (next_run, schedule_id),
                    )
                    await db.commit()
        except Exception as exc:
            logger.error("Scheduler tick error for %s: %s", schedule_id, exc)


async def _run_daily_retention() -> None:
    """Run data retention purge once per day at midnight UTC."""
    from androbugger.api.system import _DEFAULT_RETENTION, _ENTITY_TS_COL
    while True:
        try:
            await asyncio.sleep(86400)  # 24 hours
            from androbugger.db.database import get_db
            async with get_db() as db:
                rows = await (await db.execute(
                    "SELECT entity, max_age_days FROM retention_policies WHERE enabled=TRUE"
                )).fetchall()
                policies = {r["entity"]: r["max_age_days"] for r in rows}
            for entity, default_days in _DEFAULT_RETENTION.items():
                if entity not in policies:
                    policies[entity] = default_days
            async with get_db() as db:
                for entity, max_days in policies.items():
                    ts_col = _ENTITY_TS_COL[entity]
                    assert entity in _ENTITY_TS_COL
                    assert ts_col in {"started_at", "timestamp", "delivered_at", "created_at"}
                    await db.execute(
                        f"DELETE FROM {entity} WHERE {ts_col} < datetime('now', ?)",
                        (f"-{max_days} days",),
                    )
                await db.commit()
            logger.info("Daily retention purge completed")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Retention purge error: %s", exc)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve frontend static files in production
_frontend_dist = Path(__file__).parent.parent.parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
