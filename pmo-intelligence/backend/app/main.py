"""AI-Powered PMO Platform — application entry point."""
from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api, api_crud, config, models, seed
from .db import Base, SessionLocal, engine
from .services import automation, core


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.seed_reference(db)
        db.commit()
        if config.SEED_DEMO:
            seed.seed_demo(db)


def _ticker(stop: threading.Event):
    """Background scheduler: scheduled automations, report schedules, daily risk snapshot."""
    while not stop.wait(60):
        try:
            with SessionLocal() as db:
                automation.run_scheduled(db)
                core.snapshot_risks(db)
                db.commit()
        except Exception as e:  # keep ticking; the failure is visible in the server log
            print(f"[scheduler] {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.SECRET_KEY == config.DEV_SECRET:
        print("[security] PMO_SECRET_KEY is not set: using the development key. Set it before any real deployment.")
    init_db()
    stop = threading.Event()
    if config.SCHEDULER_ENABLED:
        threading.Thread(target=_ticker, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="AI-Powered PMO Platform", version="1.0.0", lifespan=lifespan)
app.include_router(api.router)
app.include_router(api_crud.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    t = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - t) * 1000:.0f}"
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    print(f"[error] {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    return JSONResponse({"detail": "Something went wrong on the server. The error was logged."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": engine.url.get_backend_name()}


# Serve the built frontend (frontend/dist) when present, with SPA fallback.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
