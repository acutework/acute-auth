"""FastAPI application entry point.

Run with:  uv run uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.onboarding_routes import (
    catalog_router,
    places_router,
    router as onboarding_router,
)
from app.api.internal_routes import router as internal_router
from app.api.routes import router as auth_router
from app.core.errors import AuthError

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Release the MSG91 HTTP clients and the Redis connection.
    from app.deps import aclose

    await aclose()


app = FastAPI(
    title="Acute Auth",
    version="0.1.0",
    description="Mobile OTP authentication and authorisation.",
    lifespan=lifespan,
)


@app.exception_handler(AuthError)
def handle_auth_error(request: Request, exc: AuthError) -> JSONResponse:
    """One place where domain errors become HTTP responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(places_router)
app.include_router(catalog_router)
# Service-to-service, key-guarded, and kept out of the public schema.
app.include_router(internal_router)
