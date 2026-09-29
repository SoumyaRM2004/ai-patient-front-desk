# AI Patient Front Desk

Multi-tenant SaaS application for clinic patient communication via WhatsApp.

> **Current status: Phase 3 — Clinic Configuration**
>
> Multi-tenant clinic configuration layer for doctors, services, and doctor working hours. All resources are strictly isolated by tenant (`clinic_id`) sourced from the authenticated JWT session. Verified with 50 automated tests and live API verification.

---

## What Works in Phase 3

- **Authentication & Multi-Tenant Foundation (Phase 2)**:
  - Clinic and owner registration (`POST /api/v1/auth/register`).
  - Argon2 password hashing (`pwdlib`) and HS256 JWT access tokens.
  - User profile and clinic context resolution (`GET /api/v1/auth/me`).
- **Doctors Management** (`/api/v1/doctors`):
  - Full CRUD (`POST`, `GET`, `PATCH`, `DELETE`) for clinic doctors.
  - Fields: `name`, `specialty`, `phone`, `email`, `is_active`.
  - Active status filtering (`?is_active=true` / `?is_active=false`).
  - Strict tenant scoping: cross-tenant access returns `404 Not Found`.
- **Services Catalog** (`/api/v1/services`):
  - Full CRUD (`POST`, `GET`, `PATCH`, `DELETE`) for clinic services.
  - Fields: `name`, `description`, `duration_minutes` (positive integer), `price` (PostgreSQL `NUMERIC(10,2)` via Python `Decimal`), `is_active`.
  - Active status filtering (`?is_active=true` / `?is_active=false`).
  - Strict tenant scoping: cross-tenant access returns `404 Not Found`.
- **Doctor Working Hours** (`/api/v1/doctors/{doctor_id}/working-hours`):
  - Full CRUD (`POST`, `GET`, `PATCH`, `DELETE`) for doctor working shifts.
  - Fields: `day_of_week` (0=Monday through 6=Sunday), `start_time` (Time), `end_time` (Time), `is_active`.
  - Supports split shifts (multiple records per doctor/day, e.g. 09:00–13:00 and 14:00–18:00).
  - Validation ensures `start_time < end_time` on creation and partial updates.
  - Double tenant verification: ensures doctor belongs to clinic before managing working hours.
  - Database-level cascade: deleting a doctor automatically removes dependent working-hour records.
- **Alembic Database Migrations**:
  - `2fef91c74a30_create_clinics_and_users.py` (Phase 2)
  - `02dc00970591_create_doctors_services_doctor_working_.py` (Phase 3)
- **Comprehensive Automated Test Suite**:
  - 50 async tests passing against isolated test database (`ai_patient_frontdesk_test`).
  - 16 tests for Phase 2 authentication and tenant isolation.
  - 34 tests for Phase 3 clinic configuration, working hours, input validation, and cascade behaviors.

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

Apply migrations to create all tables (`clinics`, `users`, `doctors`, `services`, `doctor_working_hours`):

```powershell
alembic upgrade head
```

Verify migration status:

```powershell
alembic current
```

Expected revision:
```
02dc00970591 (head)
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
============================= 50 passed in X.XXs ==============================
```

The test suite covers:
- **Authentication (16 tests)**: registration, duplicate emails, password hashing, login, tokens, `/auth/me`, and basic tenant isolation.
- **Doctors (8 tests)**: create, list, retrieve, update, delete, cross-tenant access/update/delete rejection.
- **Services (8 tests)**: create, list, retrieve, update, delete, cross-tenant access/update/delete rejection.
- **Working Hours (9 tests)**: valid creation, split shifts, invalid `day_of_week` rejection, `start_time >= end_time` rejection, list, update, delete, cross-tenant doctor creation rejection, cross-tenant access/modify rejection.
- **Input Validation (4 tests)**: non-positive duration, negative price, empty/whitespace doctor name, empty/whitespace service name.
- **Tenant Integrity & Cascade (5 tests)**: tenant identity verification on all returned items, doctor/clinic boundary enforcement, database cascade deletion, active status filtering, partial update boundary validation.

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

#### Register & Login
```powershell
$regBody = @{
  clinic_name = "Sunrise Health"
  owner_name  = "Dr. Smith"
  email       = "smith@sunrisehealth.com"
  password    = "SecurePass123"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/register -ContentType "application/json" -Body $regBody

$loginBody = @{
  email    = "smith@sunrisehealth.com"
  password = "SecurePass123"
} | ConvertTo-Json

$loginResponse = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType "application/json" -Body $loginBody
$token = $loginResponse.access_token
$headers = @{ Authorization = "Bearer $token" }
```

#### Create Doctor
```powershell
$doctorBody = @{
  name      = "Dr. Sarah Connor"
  specialty = "Cardiology"
  phone     = "+1-555-0144"
  email     = "sarah@sunrisehealth.com"
  is_active = $true
} | ConvertTo-Json

$doctor = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/doctors -Headers $headers -ContentType "application/json" -Body $doctorBody
```

#### Create Service
```powershell
$serviceBody = @{
  name             = "Cardiac Consultation"
  description      = "Comprehensive cardiovascular examination"
  duration_minutes = 45
  price            = "150.00"
  is_active        = $true
} | ConvertTo-Json

$service = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/services -Headers $headers -ContentType "application/json" -Body $serviceBody
```

#### Create Doctor Working Hours
```powershell
$whBody = @{
  day_of_week = 0
  start_time  = "09:00:00"
  end_time    = "17:00:00"
  is_active   = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/doctors/$($doctor.id)/working-hours" -Headers $headers -ContentType "application/json" -Body $whBody
```

### 4. Interactive OpenAPI Docs

Visit [http://localhost:8000/docs](http://localhost:8000/docs) in your browser. The "Authorize" button supports testing protected endpoints via Bearer token.

---

## Project Structure (Phase 3)

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
    │       ├── 2fef91c74a30_create_clinics_and_users.py
    │       └── 02dc00970591_create_doctors_services_doctor_working_.py
    ├── app/
    │   ├── main.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── auth.py              # Register, Login, Me endpoints
    │   │   ├── doctors.py           # Doctors & working hours CRUD endpoints
    │   │   └── services.py          # Services CRUD endpoints
    │   ├── core/
    │   │   ├── config.py            # App settings (Pydantic)
    │   │   └── security.py          # Argon2 hashing, HS256 JWT, get_current_user
    │   ├── db/
    │   │   ├── base.py              # DeclarativeBase
    │   │   └── session.py           # Async engine & sessionmaker
    │   ├── models/
    │   │   ├── __init__.py          # UserRole enum
    │   │   ├── clinic.py            # Clinic model (has many users, doctors, services)
    │   │   ├── doctor.py            # Doctor model (clinic FK, cascade delete)
    │   │   ├── doctor_working_hour.py # DoctorWorkingHour model (clinic & doctor FK)
    │   │   ├── service.py           # Service model (clinic FK, numeric price)
    │   │   └── user.py              # User model (clinic FK, role, hash)
    │   ├── schemas/
    │   │   ├── __init__.py
    │   │   ├── auth.py              # Auth request & response schemas
    │   │   ├── doctor.py            # Doctor create, update, response schemas
    │   │   ├── service.py           # Service create, update, response schemas
    │   │   └── working_hour.py      # Working hour create, update, response schemas
    │   └── services/
    │       ├── __init__.py
    │       ├── auth_service.py      # Auth business logic
    │       ├── doctor_service.py    # Doctor business logic & tenant isolation
    │       ├── service_service.py   # Service business logic & tenant isolation
    │       └── working_hour_service.py # Working hour business logic & validation
    └── tests/
        ├── conftest.py              # Async test fixtures, separate DB, NullPool
        ├── test_auth.py             # 16 authentication & tenant tests
        └── test_clinic_config.py    # 34 clinic configuration tests
```
