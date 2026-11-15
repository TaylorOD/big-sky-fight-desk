import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .models import Brief, Edit
from .production import Producer, fingerprint
from .provider import Provider
from .publishing import build_site, export_episode
from .storage import Budget, Store, ZONE

ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir=None, provider_factory=Provider):
    load_dotenv(ROOT / ".env")
    data_dir = data_dir or ROOT / ".local"
    store = Store(data_dir / "episodes")
    budget = Budget(data_dir / "usage.sqlite", float(os.getenv("DAILY_ALLOWANCE", "2")), float(os.getenv("MONTHLY_ALLOWANCE", "10")))
    producer = Producer(store, budget, provider_factory)
    pool = ThreadPoolExecutor(max_workers=1)
    jobs = {}
    job_lock = threading.Lock()
    token = secrets.token_urlsafe(32)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.producer = store, producer
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("x-desk-token") != token:
                return JSONResponse({"detail": "Open the studio on this computer and try again."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Only the local studio can make changes."}, status_code=403)
            if int(request.headers.get("content-length", "0")) > 50000:
                return JSONResponse({"detail": "That request is too large."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; media-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/state")
    def state():
        return {"token": token, "episodes": store.all(), "budget": budget.usage(),
                "configured": bool(os.getenv("OPENAI_API_KEY")), "today": datetime.now(ZONE).date().isoformat(),
                "busy": [key for key, future in list(jobs.items()) if not future.done()]}

    @app.post("/api/episodes")
    def create(brief: Brief):
        if brief.as_of > datetime.now(ZONE).date():
            raise ValueError("Use today or an earlier research date.")
        return store.create(brief)

    @app.post("/api/episodes/{episode_id}/{action}")
    def action(episode_id: str, action: str):
        with job_lock:
            return perform_action(episode_id, action)

    def perform_action(episode_id, action):
        if any(not future.done() for future in jobs.values()):
            raise ValueError("An operation is already running. Let it finish first.")
        store.get(episode_id)
        if action in ("draft", "review", "revise", "media"):
            def work():
                try:
                    producer.run(episode_id, action)
                except ValueError:
                    pass  # The producer persists a safe, actionable error for the UI.
            jobs[episode_id] = pool.submit(work)
            return {"started": True}
        if action == "approve":
            episode = store.get(episode_id)
            producer.require_review(episode)
            episode.update(approved=True, approval_hash=fingerprint(episode["script"]), approved_at=datetime.now(ZONE).isoformat())
            store.save(episode)
            return episode
        if action == "export":
            result = export_episode(store, episode_id, ROOT / "public")
            build_site(os.getenv("PUBLIC_URL", "https://www.taylordorsett.com/big-sky-fight-desk").rstrip("/"))
            return result
        raise ValueError("Unknown action.")

    @app.put("/api/episodes/{episode_id}")
    def edit(episode_id: str, edit: Edit):
        with job_lock:
            if any(not future.done() for future in jobs.values()):
                raise ValueError("Let the current operation finish before editing.")
            return producer.edit(episode_id, edit.script.model_dump())

    @app.get("/media/{episode_id}/{filename}")
    def media(episode_id: str, filename: str):
        episode = store.get(episode_id)
        kind = {"cover.png": "cover", "episode.mp3": "audio", "transcript.txt": None}
        if filename not in kind:
            raise HTTPException(404)
        if kind[filename] and episode.get(kind[filename] + "_hash") != fingerprint(episode.get("script")):
            raise HTTPException(404)
        path = store.folder(episode_id) / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/")
    def home():
        return FileResponse(ROOT / "web" / "studio.html")

    app.mount("/assets", StaticFiles(directory=ROOT / "web" / "shared"), name="assets")
    app.mount("/studio", StaticFiles(directory=ROOT / "web" / "studio"), name="studio")
    app.mount("/preview", StaticFiles(directory=ROOT / "dist", html=True, check_dir=False), name="preview")
    return app
