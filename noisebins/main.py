from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates

from noisebins.api.v1 import bins as bins_api
from noisebins.api.v1 import places as places_api
from noisebins.config import get_settings
from noisebins.db import get_db
from noisebins.models import Noisebin, Noiseplace
from noisebins.services.public_payload import bin_public_dict, place_public_dict
from noisebins.services.storage import get_storage
from noisebins.users import UserCreate, UserRead, UserUpdate, auth_backend, fastapi_users

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="Noisebins", version="0.1.0", docs_url="/docs", openapi_url="/openapi.json")

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )

    noiseport = APIRouter(prefix="/auth/noiseport", tags=["auth"])

    @noiseport.get("/login")
    async def noiseport_login():
        if not settings.noiseport_oauth_enabled:
            raise HTTPException(
                status.HTTP_501_NOT_IMPLEMENTED,
                "Noiseport OAuth is disabled. Set NOISEPORT_OAUTH_ENABLED=true and URLs in .env.",
            )
        if not settings.noiseport_authorize_url:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Noiseport authorize URL missing.",
            )
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Noiseport redirect is not wired in this stub — add OAuth callback routes next.",
        )

    app.include_router(noiseport)

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(places_api.router)
    api_v1.include_router(bins_api.router)
    app.include_router(api_v1)

    static_dir = BASE_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/media/{key}")
    async def serve_media(key: str):
        storage = get_storage()
        path = storage.get_path(key)
        if path is None or not path.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(path)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, db: AsyncSession = Depends(get_db)):
        r = await db.scalars(select(Noiseplace).order_by(Noiseplace.name).limit(50))
        places = [place_public_dict(p) for p in r.all()]
        return templates.TemplateResponse(request, "index.html", {"places": places})

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request):
        return templates.TemplateResponse(request, "search.html", {})

    @app.get("/b/{noisecode}", response_class=HTMLResponse)
    async def bin_page(request: Request, noisecode: str, db: AsyncSession = Depends(get_db)):
        stmt = select(Noisebin).where(Noisebin.noisecode == noisecode).options(selectinload(Noisebin.photos))
        b = await db.scalar(stmt)
        if b is None:
            raise HTTPException(404, "Bin not found")
        data = bin_public_dict(b)
        storage = get_storage()
        data["photos"] = [{"sort_order": p.sort_order, "url": storage.public_url(p.blob_key)} for p in b.photos]
        return templates.TemplateResponse(request, "bin.html", {"bin": data})

    @app.get("/bins/new", response_class=HTMLResponse)
    async def new_bin_form(request: Request, db: AsyncSession = Depends(get_db)):
        r = await db.scalars(select(Noiseplace).order_by(Noiseplace.name))
        return templates.TemplateResponse(request, "bin_new.html", {"places": [place_public_dict(p) for p in r.all()]})

    @app.post("/bins/new", response_class=HTMLResponse)
    async def new_bin_submit(
        request: Request,
        title: str = Form(...),
        noiseplace_id: str = Form(""),
        db: AsyncSession = Depends(get_db),
    ):
        """Server-rendered create requires session auth in browser — redirect to API or use JS."""
        raise HTTPException(
            401,
            "Use the API with a Bearer token or add browser session auth. Open /docs to try POST /api/v1/bins.",
        )

    return app


app = create_app()
