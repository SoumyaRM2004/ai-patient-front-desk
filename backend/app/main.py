import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.doctors import router as doctors_router
from app.api.services import router as services_router
from app.core.config import settings
from app.db.session import async_session_factory, engine

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs on startup and shutdown."""
    logger.info("Starting %s v%s", settings.app_name, settings.version)
    yield
    logger.info("Shutting down — disposing database engine")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(doctors_router)
app.include_router(services_router)


@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Verify application and database connectivity."""
    db_status = "connected"
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "disconnected"

    healthy = db_status == "connected"
    content = {
        "status": "healthy" if healthy else "unhealthy",
        "database": db_status,
        "version": settings.version,
    }

    if not healthy:
        return JSONResponse(content=content, status_code=503)
    return content
