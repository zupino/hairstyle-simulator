"""
FastAPI application factory.

Startup: initialises the SQLite database and validates required config.
Static files: /admin/* and /operator/* serve the respective SPAs.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend import config, database
from backend.routes import auth, admin, hairstyles, generation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FRONTEND_ADMIN = os.path.join(_BASE_DIR, "frontend", "admin")
_FRONTEND_OPERATOR = os.path.join(_BASE_DIR, "frontend", "operator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.SECRET_KEY or not config.BFL_API_KEY:
        raise RuntimeError("Set SECRET_KEY and BFL_API_KEY before starting the app")
    if config.BFL_MODEL not in config.MODELS:
        raise RuntimeError(f"Unsupported BFL_MODEL. Choose one of {config.MODELS}")
    logger.info("BFL image editor: %s", config.BFL_MODEL)
    database.init_db()
    password = config.credential("ADMIN_PASSWORD")
    if password:
        from backend.auth import hash_password
        username = os.getenv("ADMIN_USERNAME", "admin")
        if len(password) < 8:
            raise RuntimeError("ADMIN_PASSWORD must contain at least eight characters")
        if database.get_user_by_username(username) is None:
            database.bootstrap_admin(username, hash_password(password))
    yield


app = FastAPI(
    title="Hairstyle Simulator",
    description="Salon hairstyle visualisation API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(hairstyles.router)
app.include_router(generation.router)

# ---------------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------------
# Mount static assets (CSS/JS/images if any are added later)
if os.path.isdir(_FRONTEND_ADMIN):
    app.mount("/admin/static", StaticFiles(directory=_FRONTEND_ADMIN), name="admin-static")

if os.path.isdir(_FRONTEND_OPERATOR):
    app.mount("/operator/static", StaticFiles(directory=_FRONTEND_OPERATOR), name="operator-static")


# Serve the SPA HTML for all admin/* and operator/* paths so that
# client-side navigation works without 404s.
@app.get("/admin/{full_path:path}", include_in_schema=False)
async def serve_admin_spa(full_path: str):
    index = os.path.join(_FRONTEND_ADMIN, "index.html")
    return FileResponse(index)


@app.get("/operator/{full_path:path}", include_in_schema=False)
async def serve_operator_spa(full_path: str):
    index = os.path.join(_FRONTEND_OPERATOR, "index.html")
    return FileResponse(index)


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(os.path.join(_FRONTEND_OPERATOR, "index.html"))
