"""FastAPI app: JSON API under /api, the web UI at /."""

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, backup, config, db, extension_pairing
from .api import router


async def _auto_backup_loop():
    """Take a backup at start-up if the last one is older than a day, then check again every hour."""
    while True:
        try:
            with db.session() as conn:
                await asyncio.to_thread(backup.auto_if_due, conn)
        except Exception as exc:  # a failed backup must never stop the app
            print(f"[ConvoHub] automatic backup failed: {exc}", file=sys.stderr)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_auto_backup_loop())
    yield
    task.cancel()


app = FastAPI(title="ConvoHub", version=__version__, lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def no_stale_ui(request, call_next):
    # Without this the browser keeps an old app.js/app.css after an update. "no-cache" still allows
    # a cheap 304 when the file hasn't changed.
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "testserver"}  # testserver: FastAPI's TestClient
_LOCAL_ORIGINS = {f"http://127.0.0.1:{config.PORT}", f"http://localhost:{config.PORT}"}
_EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://")


@app.middleware("http")
async def local_only(request, call_next):
    """Keep other websites out of this local server.

    - Host check: stops DNS-rebinding (a site pointing its own domain at 127.0.0.1).
    - Origin check: a page you visit can't make your browser POST to ConvoHub (import files, change agent
      settings, approve actions). Only ConvoHub's own page may; on /api/extension/ only the paired extension.
    """
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if host not in _LOCAL_HOSTS:
        return JSONResponse({"detail": "bad host"}, status_code=400)
    origin = request.headers.get("origin")
    if origin and origin.startswith(_EXTENSION_SCHEMES) and request.url.path.startswith("/api/extension/"):
        # Only the user's own extension, identified by its ID, not any installed extension.
        ext_id = origin.split("://", 1)[1].strip("/")
        if ext_id != extension_pairing.paired_id():
            extension_pairing.note_pending(ext_id)
            return JSONResponse({
                "detail": "این افزونه هنوز توی ConvoHub تأیید نشده. صفحه‌ی ConvoHub رو باز کن و «قبول» رو بزن.",
                "unpaired": True, "extension_id": ext_id,
            }, status_code=403)
        return await call_next(request)
    if origin and request.method not in ("GET", "HEAD", "OPTIONS") and origin not in _LOCAL_ORIGINS:
        return JSONResponse({"detail": "cross-origin request blocked"}, status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
