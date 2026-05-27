"""SmartHome server entry point.

Orchestrates a list of automation packages. Each automation provides:

    init_schema()              -- create its tables (idempotent)
    router                     -- FastAPI APIRouter (already prefixed)
    lifespan_task()            -- optional async coroutine to run for the
                                  app's lifetime (cancelled cleanly on
                                  shutdown)

To add an automation: create `server/automations/<name>/` with the public
surface above, then append it to the AUTOMATIONS list below.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from automations import grid_monitor

AUTOMATIONS = [grid_monitor]

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    for auto in AUTOMATIONS:
        auto.init_schema()

    tasks: list[asyncio.Task] = []
    for auto in AUTOMATIONS:
        task_fn = getattr(auto, "lifespan_task", None)
        if task_fn is not None:
            tasks.append(asyncio.create_task(task_fn()))

    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan)

for auto in AUTOMATIONS:
    app.include_router(auto.router)


@app.get("/api/health")
async def health():
    return JSONResponse({"ok": True})


# Catch-all static mount MUST stay last — any route registered after it
# is unreachable.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
