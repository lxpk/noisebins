from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates

from noisebins.api import noiseport as noiseport_api
from noisebins.api.v1 import bins as bins_api
from noisebins.api.v1 import places as places_api
from noisebins.config import get_settings
from noisebins.db import get_db
from noisebins.models import Noisebin, Noiseplace, User
from noisebins.schemas_api import BinCreate
from noisebins.services.public_payload import bin_public_dict, place_public_dict
from noisebins.services.storage import get_storage
from noisebins.users import (
    UserCreate,
    UserRead,
    UserUpdate,
    auth_backend,
    fastapi_users,
    optional_current_user,
)

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["sso_enabled"] = settings.noiseport_oauth_enabled
templates.env.globals["sso_name"] = settings.noiseport_display_name
templates.env.globals["login_path"] = noiseport_api.login_path


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

    app.include_router(noiseport_api.router)
    app.include_router(noiseport_api.session_router)

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
    async def index(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(optional_current_user),
    ):
        r = await db.scalars(select(Noiseplace).order_by(Noiseplace.name).limit(50))
        places = [place_public_dict(p) for p in r.all()]
        return templates.TemplateResponse(request, "index.html", {"places": places, "user": user})

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, user: User | None = Depends(optional_current_user)):
        return templates.TemplateResponse(request, "search.html", {"user": user})

    @app.get("/b/{noisecode}", response_class=HTMLResponse)
    async def bin_page(
        request: Request,
        noisecode: str,
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(optional_current_user),
    ):
        stmt = select(Noisebin).where(Noisebin.noisecode == noisecode).options(selectinload(Noisebin.photos))
        b = await db.scalar(stmt)
        if b is None:
            raise HTTPException(404, "Bin not found")
        data = bin_public_dict(b)
        storage = get_storage()
        data["photos"] = [{"sort_order": p.sort_order, "url": storage.public_url(p.blob_key)} for p in b.photos]
        return templates.TemplateResponse(request, "bin.html", {"bin": data, "user": user})

    @app.get("/bins/new", response_class=HTMLResponse)
    async def new_bin_form(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(optional_current_user),
    ):
        if user is None and settings.noiseport_oauth_enabled:
            return RedirectResponse(noiseport_api.login_path("/bins/new"), status_code=status.HTTP_302_FOUND)
        r = await db.scalars(select(Noiseplace).order_by(Noiseplace.name))
        places = [place_public_dict(p) for p in r.all()]
        return templates.TemplateResponse(request, "bin_new.html", {"places": places, "user": user})

    @app.post("/bins/new", response_class=HTMLResponse)
    async def new_bin_submit(
        title: str = Form(...),
        noiseplace_id: str = Form(""),
        db: AsyncSession = Depends(get_db),
        user: User | None = Depends(optional_current_user),
    ):
        """Browser form create, authenticated by the SSO session cookie (SameSite=Lax blocks cross-site posts)."""
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to register a bin.")
        try:
            body = BinCreate(title=title.strip(), noiseplace_id=noiseplace_id or None)
        except ValidationError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, e.errors(include_url=False))
        created = await bins_api.create_bin(body, db, user)
        return RedirectResponse(f"/b/{created['noisecode']}", status_code=status.HTTP_303_SEE_OTHER)

    return app


app = create_app()
