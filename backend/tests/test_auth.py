"""Tests for authentication, authorization, and tenant isolation.

16 test cases covering:
- Registration (success, duplicate, password hashing)
- Login (success, wrong password, unknown email, inactive user)
- Protected endpoints (no token, invalid token, expired JWT, missing sub, inactive user, success)
- Tenant isolation (correct clinic association, cross-tenant verification)
"""

import uuid
from datetime import datetime, timezone, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import settings
from app.models.user import User
from tests.conftest import register_user, login_user, get_auth_header


pytestmark = pytest.mark.asyncio


# ===================================================================
# Registration
# ===================================================================


class TestRegistration:

    async def test_successful_registration(self, client: AsyncClient):
        """Registration creates a clinic and owner user, returns correct data."""
        response = await register_user(
            client,
            clinic_name="Alpha Clinic",
            owner_name="Dr. Alpha",
            email="alpha@example.com",
            password="securepass123",
        )
        assert response.status_code == 201

        data = response.json()
        assert data["clinic_name"] == "Alpha Clinic"
        assert data["user_name"] == "Dr. Alpha"
        assert data["email"] == "alpha@example.com"
        assert data["role"] == "owner"
        assert "clinic_id" in data
        assert "user_id" in data
        # Password must never be returned
        assert "password" not in data
        assert "password_hash" not in data

    async def test_duplicate_email_registration(self, client: AsyncClient):
        """Registering with an already-used email returns 409."""
        await register_user(
            client,
            clinic_name="First Clinic",
            owner_name="First Owner",
            email="duplicate@example.com",
            password="password1234",
        )

        response = await register_user(
            client,
            clinic_name="Second Clinic",
            owner_name="Second Owner",
            email="duplicate@example.com",
            password="password5678",
        )
        assert response.status_code == 409

    async def test_password_stored_as_hash(self, client: AsyncClient, db_session):
        """The database stores an Argon2 hash, not the plaintext password."""
        await register_user(
            client,
            clinic_name="Hash Clinic",
            owner_name="Hash Owner",
            email="hash@example.com",
            password="plaintextpassword",
        )

        result = await db_session.execute(
            select(User).where(User.email == "hash@example.com")
        )
        user = result.scalar_one_or_none()

        assert user is not None
        assert user.password_hash != "plaintextpassword"
        assert user.password_hash.startswith("$argon2")

    async def test_short_password_rejected(self, client: AsyncClient):
        """Password shorter than 8 characters is rejected."""
        response = await register_user(
            client,
            clinic_name="Short Clinic",
            owner_name="Short Owner",
            email="short@example.com",
            password="short",
        )
        assert response.status_code == 422


# ===================================================================
# Login
# ===================================================================


class TestLogin:

    async def test_successful_login(self, client: AsyncClient):
        """Valid credentials return an access token."""
        await register_user(
            client,
            clinic_name="Login Clinic",
            owner_name="Login Owner",
            email="login@example.com",
            password="loginpass123",
        )

        response = await login_user(client, "login@example.com", "loginpass123")
        assert response.status_code == 200

        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_invalid_password(self, client: AsyncClient):
        """Wrong password returns 401 with a generic message."""
        await register_user(
            client,
            clinic_name="Bad Pass Clinic",
            owner_name="Bad Pass Owner",
            email="badpass@example.com",
            password="correctpassword",
        )

        response = await login_user(client, "badpass@example.com", "wrongpassword")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"

    async def test_unknown_email(self, client: AsyncClient):
        """Non-existent email returns the same 401 as wrong password."""
        response = await login_user(client, "unknown@example.com", "anypassword")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"

    async def test_inactive_user_login(self, client: AsyncClient, db_session):
        """Inactive user gets the same generic 401 (no info leak)."""
        await register_user(
            client,
            clinic_name="Inactive Clinic",
            owner_name="Inactive Owner",
            email="inactive@example.com",
            password="activepass123",
        )

        # Deactivate user
        await db_session.execute(
            update(User)
            .where(User.email == "inactive@example.com")
            .values(is_active=False)
        )
        await db_session.commit()

        response = await login_user(client, "inactive@example.com", "activepass123")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


# ===================================================================
# Protected endpoint (/auth/me)
# ===================================================================


class TestProtectedEndpoint:

    async def test_no_token(self, client: AsyncClient):
        """Request without Authorization header returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_invalid_token(self, client: AsyncClient):
        """Malformed token returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert response.status_code == 401

    async def test_expired_jwt(self, client: AsyncClient):
        """Expired JWT returns 401."""
        expired_payload = {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401

    async def test_jwt_missing_sub(self, client: AsyncClient):
        """JWT without 'sub' claim returns 401."""
        no_sub_payload = {
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        no_sub_token = jwt.encode(
            no_sub_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {no_sub_token}"},
        )
        assert response.status_code == 401

    async def test_inactive_user_valid_token(self, client: AsyncClient, db_session):
        """Valid JWT for an inactive user returns 401."""
        await register_user(
            client,
            clinic_name="Deact Clinic",
            owner_name="Deact Owner",
            email="deact@example.com",
            password="deactpass123",
        )

        # Get a valid token first
        headers = await get_auth_header(client, "deact@example.com", "deactpass123")

        # Deactivate the user
        await db_session.execute(
            update(User)
            .where(User.email == "deact@example.com")
            .values(is_active=False)
        )
        await db_session.commit()

        # Token is still valid but user is inactive
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401

    async def test_valid_token_returns_user(self, client: AsyncClient):
        """Valid JWT returns correct user profile with clinic info."""
        reg_response = await register_user(
            client,
            clinic_name="Me Clinic",
            owner_name="Me Owner",
            email="me@example.com",
            password="mepassword123",
        )
        reg_data = reg_response.json()

        headers = await get_auth_header(client, "me@example.com", "mepassword123")
        response = await client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["name"] == "Me Owner"
        assert data["role"] == "owner"
        assert data["is_active"] is True
        assert data["clinic_id"] == reg_data["clinic_id"]
        assert data["clinic_name"] == "Me Clinic"
        # Password must never appear
        assert "password" not in data
        assert "password_hash" not in data


# ===================================================================
# Tenant Isolation
# ===================================================================


class TestTenantIsolation:

    async def test_user_belongs_to_correct_clinic(self, client: AsyncClient):
        """Authenticated user's clinic_id matches the clinic created at registration."""
        reg_response = await register_user(
            client,
            clinic_name="Tenant A Clinic",
            owner_name="Tenant A Owner",
            email="tenanta@example.com",
            password="tenantapass123",
        )
        reg_data = reg_response.json()

        headers = await get_auth_header(client, "tenanta@example.com", "tenantapass123")
        me_response = await client.get("/api/v1/auth/me", headers=headers)
        me_data = me_response.json()

        assert me_data["clinic_id"] == reg_data["clinic_id"]
        assert me_data["clinic_name"] == "Tenant A Clinic"

    async def test_separate_tenants_isolated(self, client: AsyncClient):
        """Two separate registrations produce two isolated tenant contexts."""
        # Register tenant A
        reg_a = await register_user(
            client,
            clinic_name="Clinic A",
            owner_name="Owner A",
            email="ownera@example.com",
            password="passworda123",
        )
        data_a = reg_a.json()

        # Register tenant B
        reg_b = await register_user(
            client,
            clinic_name="Clinic B",
            owner_name="Owner B",
            email="ownerb@example.com",
            password="passwordb123",
        )
        data_b = reg_b.json()

        # Clinics must be different
        assert data_a["clinic_id"] != data_b["clinic_id"]

        # User A sees clinic A
        headers_a = await get_auth_header(client, "ownera@example.com", "passworda123")
        me_a = await client.get("/api/v1/auth/me", headers=headers_a)
        assert me_a.json()["clinic_id"] == data_a["clinic_id"]
        assert me_a.json()["clinic_name"] == "Clinic A"

        # User B sees clinic B
        headers_b = await get_auth_header(client, "ownerb@example.com", "passwordb123")
        me_b = await client.get("/api/v1/auth/me", headers=headers_b)
        assert me_b.json()["clinic_id"] == data_b["clinic_id"]
        assert me_b.json()["clinic_name"] == "Clinic B"

        # User A cannot see clinic B data and vice versa
        assert me_a.json()["clinic_id"] != me_b.json()["clinic_id"]
