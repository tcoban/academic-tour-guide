from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.services.seed import seed_reference_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_production_ready()
    init_db()
    with SessionLocal() as session:
        seed_reference_data(session)
        session.commit()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_api_access_token(request: Request, call_next):
    access_token = settings.access_token
    if access_token and request.url.path.startswith(settings.api_prefix) and request.url.path != f"{settings.api_prefix}/health":
        provided = request.headers.get("x-atg-api-key")
        if provided != access_token:
            return JSONResponse({"detail": "Roadshow API access token required."}, status_code=401)
    return await call_next(request)


app.include_router(router, prefix=settings.api_prefix)
