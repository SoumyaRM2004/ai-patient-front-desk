# AI Patient Front Desk

Multi-tenant SaaS application for clinic patient communication via WhatsApp.

> **Current status: Phase 2 — Authentication & Multi-Tenant Architecture**
>
> Multi-tenant foundation with clinic registration, owner accounts, Argon2 password hashing, HS256 JWT tokens, and strict tenant isolation. Verified with 16 automated tests.

---

## What Works in Phase 2

- **Clinic & User Registration** (`POST /api/v1/auth/register`): Atomic transaction creating clinic + owner user with password hashed via Argon2 (`pwdlib`).
- **Authentication & Login** (`POST /api/v1/auth/login`): Verifies credentials, returns signed HS256 JWT containing `sub` (user UUID), `iat`, and `exp`.
- **Protected Endpoints** (`GET /api/v1/auth/me`): Validates Bearer token via `OAuth2PasswordBearer`, verifies user active status and loads clinic context.
- **Tenant Isolation**: Foreign key constraints and `clinic_id` scoping ensure clinics cannot access data outside their organization.
- **Alembic Database Migrations**: Auto-generated revision `2fef91c74a30_create_clinics_and_users.py` with timezone-aware timestamp columns.
- **Comprehensive Automated Test Suite**: 16 async tests running against isolated test database (`ai_patient_frontdesk_test`).

---

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 17** (installed and running as a Windows service)
- **Git**

---

## Setup Instructions

### 1. Create the Databases (Main + Test)

Open Windows PowerShell and connect to your local PostgreSQL server:

```powershell
psql -U postgres
```

Enter your PostgreSQL password when prompted. Then create both databases:

```sql
CREATE DATABASE ai_patient_frontdesk;
CREATE DATABASE ai_patient_frontdesk_test;
```

Verify both were created:

```sql
\l
```

Exit `psql`:

```sql
\q
```

### 2. Virtual Environment & Dependencies

From the `backend/` directory:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Configure Environment Variables

```powershell
Copy-Item .env.example .env
```

Edit `backend/.env` with your actual PostgreSQL credentials and a secure dev JWT secret (minimum 32 bytes):

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/ai_patient_frontdesk
TEST_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/ai_patient_frontdesk_test

APP_NAME=AI Patient Front Desk
VERSION=0.1.0
DEBUG=true

JWT_SECRET_KEY=dev-secret-key-change-this-in-production-minimum-32-bytes
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 4. Run Database Migrations

Apply the migration to create `clinics` and `users` tables:

```powershell
alembic upgrade head
```

Verify migration status:

```powershell
alembic current
```

---

## Verification

### 1. Run Automated Test Suite

Run the full async test suite against the test database:

```powershell
pytest -v
```

**Expected output:**
```
============================= 16 passed in X.XXs ==============================
```

All 16 test cases cover:
- Registration success, duplicate email rejection, Argon2 hashing, password length validation
- Login success, invalid credentials, inactive user rejection
- Token validation (missing token, invalid signature, expired token, missing `sub`, inactive user with valid token)
- Tenant isolation (separate clinics isolated, user belongs to correct clinic)

### 2. Start the Application

```powershell
uvicorn app.main:app --reload --port 8000
```

### 3. Test Endpoints

#### Health Check
```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```
Response:
```json
{"status": "healthy", "database": "connected", "version": "0.1.0"}
```

#### Register Clinic & Owner
```powershell
$body = @{
  clinic_name = "Sunrise Health"
  owner_name  = "Dr. Smith"
  email       = "smith@sunrisehealth.com"
  password    = "SecurePass123"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/register -ContentType "application/json" -Body $body
```

#### Login & Retrieve Current User
```powershell
$loginBody = @{
  email    = "smith@sunrisehealth.com"
  password = "SecurePass123"
} | ConvertTo-Json

$loginResponse = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType "application/json" -Body $loginBody
$token = $loginResponse.access_token

Invoke-RestMethod -Method Get -Uri http://localhost:8000/api/v1/auth/me -Headers @{ Authorization = "Bearer $token" }
```

### 4. Interactive OpenAPI Docs

Visit [http://localhost:8000/docs](http://localhost:8000/docs) in your browser. The "Authorize" button supports testing protected endpoints via Bearer token.

---

## Project Structure (Phase 2)

```
AI Patient Front Desk/
├── docker-compose.yml
├── README.md
├── .gitignore
└── backend/
    ├── .env.example
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── pyproject.toml
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py
    │   └── versions/
    │       └── 2fef91c74a30_create_clinics_and_users.py
    ├── app/
    │   ├── main.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── auth.py              # Register, Login, Me endpoints
    │   ├── core/
    │   │   ├── config.py            # App settings (Pydantic)
    │   │   └── security.py          # Argon2 hashing, HS256 JWT, get_current_user
    │   ├── db/
    │   │   ├── base.py              # DeclarativeBase
    │   │   └── session.py           # Async engine & sessionmaker
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── clinic.py            # Clinic model
    │   │   └── user.py              # User model (clinic FK, role, hash)
    │   ├── schemas/
    │   │   ├── __init__.py
    │   │   └── auth.py              # Pydantic schemas (requests/responses)
    │   └── services/
    │       ├── __init__.py
    │       └── auth_service.py      # Business logic (register, authenticate)
    └── tests/
        ├── conftest.py              # Async test fixtures, separate DB, NullPool
        └── test_auth.py             # 16 test cases
```
