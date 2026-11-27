"""
main.py
-------
FastAPI application entrypoint. Assembles the v1 address + digipin
routers, applies CORS from config, and exposes a liveness endpoint.

Run with:
    uvicorn main:app --reload --port 8000

Interactive OpenAPI docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.address import router as address_router
from api.v1.digipin import router as digipin_router
from config import settings
from logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger("main")

app = FastAPI(
    title="AI-DIGIPIN Address Intelligence API",
    description=(
        "API-first infrastructure layer that transforms unstructured Indian "
        "addresses into validated, structured, confidence-scored and "
        "DIGIPIN-linked delivery points for last-mile logistics, e-commerce, "
        "and food-delivery platforms."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(address_router)
app.include_router(digipin_router)


@app.on_event("startup")
async def on_startup():
    if not settings.auth_enabled():
        logger.warning(
            "No API_KEYS configured -- running with authentication DISABLED. "
            "Set API_KEYS in your environment before deploying beyond local dev."
        )
    if settings.cors_allow_origins == ["*"]:
        logger.warning(
            "CORS_ALLOW_ORIGINS is wide open ('*') -- fine for local dev, "
            "must be restricted before production deployment."
        )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1")
async def api_info():
    return {
        "name": "AI-DIGIPIN Address Intelligence API",
        "version": "2.0.0",
        "endpoints": [
            "POST /api/v1/address/parse",
            "POST /api/v1/address/validate",
            "POST /api/v1/address/resolve",
            "GET  /api/v1/digipin/{code}",
            "POST /api/v1/digipin/decode",
        ],
        "docs": "/docs",
    }
