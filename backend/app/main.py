"""FastAPI app: wires store, event bus, pipeline runner and serves the built React UI."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import jobs_routes, system_routes
from .config import ROOT, AppConfig, load_config
from .event_bus import EventBus
from .job_store import JobStore
from .link_job_actions import LinkJobActions
from .pipeline_runner import PipelineRunner
from .steps.step_registry import build_steps
from .telegram.telegram_listener import TelegramListener
from .telegram.telegram_setup import start_telegram

FRONTEND_DIST = ROOT / "frontend" / "dist"


@dataclass
class Services:
    config: AppConfig
    store: JobStore
    bus: EventBus
    runner: PipelineRunner
    actions: LinkJobActions
    telegram: TelegramListener | None = None


LOCAL_HOSTS = ["127.0.0.1", "localhost"]
DEV_PORT = 5173  # Vite dev server


def create_app(config: AppConfig | None = None, steps=None, start_worker: bool = True,
               allowed_hosts: list[str] | None = None) -> FastAPI:
    config = config or load_config()
    store = JobStore(config.paths.jobs_dir)
    bus = EventBus()
    runner = PipelineRunner(store, bus, config, steps or build_steps())
    services = Services(config, store, bus, runner, LinkJobActions(store, runner, config))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        runner.recover()
        if start_worker:
            runner.start()
            services.telegram = start_telegram(config, services.actions)
        yield
        runner.stop()
        if services.telegram:
            services.telegram.stop()

    app = FastAPI(title="AI Video Creator", lifespan=lifespan)
    app.state.services = services

    # Only this machine's own UI may drive the API: block other sites (CSRF) and DNS rebinding.
    hosts = allowed_hosts or LOCAL_HOSTS
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    origins = {f"http://{h}:{p}" for h in LOCAL_HOSTS for p in (config.server.port, DEV_PORT)}

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in origins:
            return JSONResponse({"detail": "Origin không được phép"}, status_code=403)
        return await call_next(request)

    app.include_router(jobs_routes.router)
    app.include_router(system_routes.router)

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
