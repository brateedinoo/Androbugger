"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from androbugger.api import auth, chat, commands, devices, diagnostics, knowledge, logcat, plugins as plugins_api
from androbugger.config import settings
from androbugger.db.database import init_db
from androbugger.db.seed import seed_defaults
from androbugger.device import adb as adb_module
from androbugger.device import manager
from androbugger.device.models import DeviceInfo

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

    # Load permission tiers from DB
    from androbugger.db.database import get_db
    async with get_db() as db:
        rows = await (await db.execute("SELECT * FROM command_permissions")).fetchall()
        adb_module.load_permission_tiers([dict(r) for r in rows])

    # Load plugins
    from androbugger.plugins.loader import load_all_plugins
    plugins_dir = Path(__file__).parent.parent.parent.parent.parent / "plugins"
    load_all_plugins(plugins_dir)

    # Register device status broadcast callback
    manager.add_status_callback(devices.broadcast_device_event)

    # Start background device polling
    poll_task = asyncio.create_task(manager.poll_devices())
    logger.info("Device polling started")

    yield

    poll_task.cancel()
    try:
        await poll_task
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

# WebSocket routes (logcat, chat) already registered via router includes
app.include_router(logcat.router)

# WebSocket route for device status (prefix-less — registered in devices.py)
# Note: /ws/devices is handled inside devices.py but needs mounting at app level
app.add_api_websocket_route("/ws/devices", devices.ws_devices)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve frontend static files in production
_frontend_dist = Path(__file__).parent.parent.parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
