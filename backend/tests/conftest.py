"""Test fixtures for the AI Patient Front Desk test suite.

Uses a separate test database (ai_patient_frontdesk_test) to avoid
corrupting development data. Tables are created once per session;
data is cleaned up after each test via DELETE.

Key design: the app and tests use INDEPENDENT sessions from the same
test session factory. No session is shared between the ASGI app and
the test code, avoiding asyncpg's "another operation is in progress" error.
"""

import asyncio
import os
from collections.abc import AsyncGenerator

# Set test environment variables BEFORE importing app modules.
# JWT secret must be >= 32 bytes. This value is clearly development-only.
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-jwt-secret-key-do-not-use-in-production-minimum-32-bytes",
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db

# Import all models so Base.metadata includes their tables
from app.models.clinic import Clinic  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.doctor import Doctor  # noqa: F401
from app.models.service import Service  # noqa: F401
from app.models.doctor_working_hour import DoctorWorkingHour  # noqa: F401


# ---------------------------------------------------------------------------
# Test database configuration
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_patient_frontdesk_test",
)

# NullPool: each connect() creates a fresh connection, never reuses across
# event loops. Eliminates cross-loop issues between session fixture and tests.
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Table lifecycle (session-scoped, sync fixture using asyncio.run)
# ---------------------------------------------------------------------------

async def _create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once at session start, drop at session end."""
    asyncio.run(_create_tables())
    yield
    asyncio.run(_drop_tables())


@pytest_asyncio.fixture(autouse=True)
async def clean_data(setup_database):
    """Delete all row data after each test for isolation.

    Deletes in FK-safe order:
    1. doctor_working_hours (has FK to doctors and clinics)
    2. doctors (has FK to clinics)
    3. services (has FK to clinics)
    4. users (has FK to clinics)
    5. clinics
    """
    yield
    async with test_engine.begin() as conn:
        await conn.execute(text("DELETE FROM doctor_working_hours"))
        await conn.execute(text("DELETE FROM doctors"))
        await conn.execute(text("DELETE FROM services"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM clinics"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Independent session for direct DB inspection/mutation in tests.

    This session is separate from the app's sessions. Changes made here
    must be committed to be visible to the app's sessions.
    """
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client. The app gets its own independent session per request.

    The dependency override replaces get_db so the app uses the test database,
    but each request handler gets a fresh session — no sharing with test code.
    """
    from app.main import app

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

async def register_user(
    client: AsyncClient,
    clinic_name: str = "Test Clinic",
    owner_name: str = "Test Owner",
    email: str = "owner@testclinic.com",
    password: str = "testpassword123",
):
    """Register a clinic and owner user, return the raw response."""
    return await client.post(
        "/api/v1/auth/register",
        json={
            "clinic_name": clinic_name,
            "owner_name": owner_name,
            "email": email,
            "password": password,
        },
    )


async def login_user(
    client: AsyncClient,
    email: str = "owner@testclinic.com",
    password: str = "testpassword123",
):
    """Log in a user and return the raw response."""
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


async def get_auth_header(
    client: AsyncClient,
    email: str = "owner@testclinic.com",
    password: str = "testpassword123",
) -> dict:
    """Log in and return an Authorization header dict."""
    response = await login_user(client, email, password)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
