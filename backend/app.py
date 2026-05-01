import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.db import init_db, test_connection, init_pool, close_pool  # type: ignore
from src.api import (  # type: ignore
    campaigns_router,
    leads_router,
    leads_detail_router,
    documents_library_router,
    documents_attach_router,
)
from src.auth import auth_router  # type: ignore
from src.scheduler import start_scheduler, stop_scheduler  # type: ignore

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    if test_connection():
        init_db()
        start_scheduler()
    yield
    stop_scheduler()
    close_pool()


app = FastAPI(
    title="AI Mail Personalization",
    description="Multi-tenant SaaS for automated personalized email outreach",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS origins from environment, comma-separated
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000")
CORS_ORIGINS = [origin.strip() for origin in _raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes live under /api so Caddy can reverse-proxy them
# while serving the frontend static files on everything else.
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(campaigns_router)
api_router.include_router(leads_router)
api_router.include_router(leads_detail_router)
api_router.include_router(documents_library_router)
api_router.include_router(documents_attach_router)


@api_router.get("/health")
async def health_check():
    db_connected = test_connection()
    return {
        "status": "healthy" if db_connected else "degraded",
        "database": "connected" if db_connected else "disconnected",
    }


@api_router.get("/")
async def root():
    return {"message": "AI Mail Personalization API", "version": "2.0.0"}


app.include_router(api_router)
