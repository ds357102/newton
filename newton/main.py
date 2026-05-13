"""FastAPI app entrypoint."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .api import (
    ticker, feed, watchlists, ideas, automation,
    prospects, recommendations, voice, alf_actions, dashboard,
)

log = logging.getLogger("newton.main")


async def _background_alf_sync():
    """Refresh prospects from ALF on startup, then every settings.alf_sync_interval_sec.
    Cheap: one HTTPS call to ALF. Safe to run alongside everything else."""
    if not settings.alf_api_url or not settings.newton_api_token:
        log.info("ALF sync disabled (set ALF_API_URL + NEWTON_API_TOKEN to enable)")
        return
    from .prospects.source import prospect_source
    log.info(f"ALF sync starting (every {settings.alf_sync_interval_sec}s)")
    while True:
        try:
            n = await prospect_source.refresh_from_alf()
            log.info(f"ALF sync cycle: {n} prospects in cache")
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.exception(f"ALF sync failed: {e}")
        try:
            await asyncio.sleep(settings.alf_sync_interval_sec)
        except asyncio.CancelledError:
            return


async def _background_streamer():
    """In-process streamer loop. Runs every NEWTON_STREAM_INTERVAL_SEC seconds.

    Single-service deploys (Railway/Render/Fly) use this so the streamer's
    writes share memory with the web service. For larger scale, set
    NEWTON_DISABLE_INPROCESS_STREAMER=1 and run `python -m workers.streamer`
    in a separate service against a shared volume or Redis-backed store.
    """
    if os.environ.get("NEWTON_DISABLE_INPROCESS_STREAMER"):
        log.info("in-process streamer disabled by env")
        return
    try:
        from workers.streamer import cycle, persist, INTERVAL
        from .store import hits as hits_store
    except Exception as e:
        log.warning(f"streamer import failed; skipping background loop: {e}")
        return

    log.info(f"in-process streamer starting (interval={INTERVAL}s)")
    while True:
        try:
            new_hits = await cycle()
            hits_store.replace_all(new_hits)
            persist(new_hits)
        except asyncio.CancelledError:
            log.info("in-process streamer cancelled cleanly")
            return
        except Exception as e:
            log.exception(f"streamer cycle failed: {e}")
        try:
            await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort first sync from ALF before yielding so the UI loads with real
    # prospects on the very first request, not the stub list.
    if settings.alf_api_url and settings.newton_api_token:
        try:
            from .prospects.source import prospect_source
            n = await prospect_source.refresh_from_alf()
            log.info(f"ALF initial sync at startup: {n} prospects loaded")
        except Exception as e:
            log.warning(f"ALF initial sync failed: {e}")

    streamer_task = asyncio.create_task(_background_streamer())
    alf_task = asyncio.create_task(_background_alf_sync())
    try:
        yield
    finally:
        for t in (streamer_task, alf_task):
            t.cancel()
        for t in (streamer_task, alf_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="Newton — Current Events", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(ticker.router, prefix="/ticker", tags=["ticker"])
app.include_router(feed.router, prefix="/feed", tags=["feed"])
app.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
app.include_router(ideas.router, prefix="/ideas", tags=["ideas"])
app.include_router(automation.router, prefix="/automation", tags=["automation"])
app.include_router(prospects.router, prefix="/prospects", tags=["prospects"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(alf_actions.router, prefix="/alf", tags=["alf"])
app.include_router(dashboard.router, prefix="/current-events", tags=["dashboard"])


# Static UI ---
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "newton", "web")
if not os.path.isdir(WEB_DIR):
    WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(WEB_DIR):
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
async def root():
    index = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"service": "newton", "msg": "no UI mounted; see /docs"}


@app.get("/healthz")
async def healthz():
    from .store import hits as hits_store
    from .prospects.source import prospect_source
    return {
        "ok": True,
        "service": "newton",
        "version": app.version,
        "env": settings.env,
        "llm_configured": bool(settings.anthropic_api_key),
        "alf_configured": bool(settings.alf_api_url and settings.newton_api_token),
        "cached_prospects": len(prospect_source._sample),
        "cached_owners": len(prospect_source._owners),
        "cached_hits": hits_store.total_count(),
    }
