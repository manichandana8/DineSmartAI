from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import bookings, feedback, profile, recommend, ws_chat
from app.api.routes.diagnostics import router as diagnostics_router, run_google_places_diagnostic
from app.config import get_settings
from app.db import init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHAT_UI = PROJECT_ROOT / "static" / "index.html"
MARKETING_DIST = PROJECT_ROOT / "web" / "dist"
MARKETING_INDEX = MARKETING_DIST / "index.html"
MARKETING_ASSETS = MARKETING_DIST / "assets"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="DineSmartAI",
    description="AI dining concierge — REST + WebSocket text chat (Gemini or OpenAI for LLM).",
    version="0.2.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_hosts = _settings.trusted_host_list()
if _hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

app.include_router(diagnostics_router)
app.include_router(bookings.router)
app.include_router(recommend.router)
app.include_router(feedback.router)
app.include_router(profile.router)
app.include_router(ws_chat.router)

if MARKETING_INDEX.is_file():
    if MARKETING_ASSETS.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(MARKETING_ASSETS)),
            name="marketing_assets",
        )

    def _marketing_spa_index() -> FileResponse:
        return FileResponse(MARKETING_INDEX)

    for _path in ("/sign-in", "/sign-up"):
        app.add_api_route(
            _path,
            _marketing_spa_index,
            methods=["GET"],
            include_in_schema=False,
        )

    @app.get("/favicon.svg", include_in_schema=False, response_model=None)
    def marketing_favicon() -> FileResponse:
        icon = MARKETING_DIST / "favicon.svg"
        if not icon.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(icon)


@app.get("/assistant", include_in_schema=False, response_model=None)
def assistant_chat_ui() -> Union[FileResponse, RedirectResponse]:
    """DineSmartAI AI chat UI."""
    if CHAT_UI.is_file():
        return FileResponse(CHAT_UI)
    return RedirectResponse(url="/docs")


@app.get("/", include_in_schema=False, response_model=None)
def root() -> Union[FileResponse, RedirectResponse]:
    """DineSmartAI marketing site when web/dist exists; else DineSmartAI chat UI."""
    if MARKETING_INDEX.is_file():
        return FileResponse(MARKETING_INDEX)
    if CHAT_UI.is_file():
        return FileResponse(CHAT_UI)
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/smartdine-ping", include_in_schema=False)
def smartdine_ping() -> dict[str, str]:
    """If this 404s, you are not talking to DineSmartAI (wrong port, old server, or different app)."""
    return {"app": "smartdine", "ok": True}


@app.get("/debug", include_in_schema=False, response_class=HTMLResponse)
def debug_home() -> str:
    """Human-friendly page so you know the URL and server are correct."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>DineSmartAI — Debug</title>
<style>body{font-family:system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;}
a{color:#0b57d0;} code{background:#f1f3f4;padding:0 .2rem;}</style></head><body>
<h1>DineSmartAI backend</h1>
<p>If you see this page, your browser is hitting <strong>this</strong> FastAPI app.</p>
<ul>
  <li><a href="/smartdine-ping">/smartdine-ping</a> — should show JSON with <code>"app":"smartdine"</code></li>
  <li><a href="/debug/places">/debug/places</a> — Google Places diagnostics (JSON)</li>
  <li><a href="/v1/diagnostics/google-places">/v1/diagnostics/google-places</a> — same JSON</li>
  <li><a href="/health">/health</a></li>
  <li><a href="/">/</a> — marketing when <code>web/dist</code> exists, else chat UI</li>
  <li><a href="/assistant">/assistant</a> — DineSmartAI AI chat</li>
  <li><a href="/docs">/docs</a> — Swagger</li>
</ul>
<p><strong>Still get <code>{"detail":"Not Found"}</code>?</strong> You are on the wrong address.
Use the URL printed in the terminal when you run <code>python main.py</code> (e.g. <code>http://127.0.0.1:8000/debug</code> — note the port).</p>
</body></html>"""


@app.get("/diagnostics/google-places", include_in_schema=False, response_model=None)
async def diagnostics_google_places_shortcut() -> dict:
    return await run_google_places_diagnostic()


@app.get("/debug/places", include_in_schema=False, response_model=None)
async def debug_places_shortcut() -> dict:
    return await run_google_places_diagnostic()


@app.get("/diagnostics/google-places/", include_in_schema=False, response_model=None)
@app.get("/debug/places/", include_in_schema=False, response_model=None)
async def diagnostics_trailing_slash() -> dict:
    return await run_google_places_diagnostic()
