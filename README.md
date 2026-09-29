# AI Patient Front Desk

Multi-tenant SaaS application for clinic patient communication via WhatsApp.

> **Current status: Phase 4 — Patients & Appointments**
>
> Multi-tenant deterministic patient and appointment booking foundation. Appointments are strictly validated against doctor working hours, service duration, and existing non-cancelled bookings. Concurrency-safe double-booking prevention is enforced via PostgreSQL row-level locking (`SELECT ... FOR UPDATE`). All resources are isolated by tenant (`clinic_id`) sourced from the authenticated JWT session. Verified with 107 automated tests and live API verification.

---

## What Works in Phase 4

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
- **Patients Management** (`/api/v1/patients`):
  - Full CRUD (`POST`, `GET`, `PATCH`, `DELETE` via soft deactivation) for clinic patients.
  - Fields: `full_name`, `phone`, `email`, `date_of_birth`, `gender`, `notes`, `is_active`.
  - Patient search query parameter (`?q=`) across full name, phone number, and email.
  - Active status filtering (`?is_active=true` / `?is_active=false`).
  - Phone uniqueness strictly scoped per clinic (`UniqueConstraint("clinic_id", "phone")`).
  - Soft deactivation: `DELETE /api/v1/patients/{id}` sets `is_active=False` rather than deleting records.
- **Appointments Management** (`/api/v1/appointments`):
  - Management endpoints (`POST`, `GET`, `PATCH`, `POST /cancel`) for clinic appointments (no physical delete endpoint exists; historical records are strictly preserved).
  - Status lifecycle: `SCHEDULED` -> `CONFIRMED` -> `COMPLETED` / `NO_SHOW`, or `SCHEDULED` / `CONFIRMED` -> `CANCELLED`.
  - Cancellation endpoint: `POST /api/v1/appointments/{id}/cancel` (sets status to `CANCELLED` and frees up slot).
  - Rescheduling endpoint: `PATCH /api/v1/appointments/{id}/reschedule` (updates start/end times with conflict validation).
  - End time is strictly derived by the backend from `service.duration_minutes`; clients cannot submit arbitrary end times.
  - Status/Doctor/Patient/Date range filtering on list endpoint.
- **Deterministic Availability Engine** (`GET /api/v1/appointments/available-slots`):
  - Computes candidate slots given `doctor_id`, `service_id`, and `date`.
  - Supports split shifts (break periods between shifts produce no slots).
  - Configurable slot interval (defaults to 15 minutes).
  - Slot candidate fits strictly inside doctor's working shifts: `candidate_start >= shift_start` and `candidate_end <= shift_end`.
  - Timezone-aware slot generation using clinic's configured timezone (e.g. `Asia/Kolkata`).
  - Rejects past date/time slots and filters out overlapping non-cancelled bookings.
- **Concurrency Safety & Conflict Detection**:
  - Overlap condition: `existing.start_at < requested_end AND existing.end_at > requested_start`.
  - Ignores cancelled appointments (`status != 'cancelled'`).
  - Atomic double-booking prevention via `select(Doctor.id).with_for_update()` inside database transaction.
  - Foreign key safety: Appointments use `ondelete="RESTRICT"` for patient, doctor, and service to preserve medical history.
- **Alembic Database Migrations**:
  - `2fef91c74a30_create_clinics_and_users.py` (Phase 2)
  - `02dc00970591_create_doctors_services_doctor_working_.py` (Phase 3)
  - `23098df46eaf_create_patients_and_appointments.py` (Phase 4)
- **Comprehensive Automated Test Suite**:
  - 107 async tests passing against isolated test database (`ai_patient_frontdesk_test`).
  - 16 tests for Phase 2 authentication and tenant isolation.
  - 34 tests for Phase 3 clinic configuration, working hours, and cascades.
  - 57 tests for Phase 4 patients, appointments, availability engine, concurrency, and validation.

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

Apply migrations to create all tables (`clinics`, `users`, `doctors`, `services`, `doctor_working_hours`, `patients`, `appointments`):

```powershell
alembic upgrade head
```

Verify migration status:

```powershell
alembic current
```

Expected revision:
```
23098df46eaf (head)
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
============================ 107 passed in X.XXs ==============================
```

The test suite covers:
- **Authentication (16 tests)**: registration, duplicate emails, password hashing, login, tokens, `/auth/me`, and basic tenant isolation.
- **Doctors (8 tests)**: create, list, retrieve, update, delete, cross-tenant access/update/delete rejection.
- **Services (8 tests)**: create, list, retrieve, update, delete, cross-tenant access/update/delete rejection.
- **Working Hours (9 tests)**: valid creation, split shifts, invalid `day_of_week` rejection, `start_time >= end_time` rejection, list, update, delete, cross-tenant doctor creation rejection, cross-tenant access/modify rejection.
- **Input Validation (4 tests)**: non-positive duration, negative price, empty/whitespace doctor name, empty/whitespace service name.
- **Tenant Integrity & Cascade (5 tests)**: tenant identity verification on all returned items, doctor/clinic boundary enforcement, database cascade deletion, active status filtering, partial update boundary validation.
- **Patients (10 tests)**: create, list, retrieve, update, soft deactivation, search by name/phone/email, phone uniqueness scoped per clinic, duplicate phone rejection within clinic, cross-tenant access/update/deactivation rejection.
- **Appointments (18 tests)**: create, retrieve, update, reschedule, cancel, list with filters (doctor, patient, status, date range), cross-tenant isolation on all operations.
- **Availability Engine (10 tests)**: candidate slot generation, split shifts (no slots in break), doctor working hours bounds, timezone handling, booked slot exclusion, past slots filtering, service duration boundaries.
- **Conflict & Concurrency (9 tests)**: exact start overlap, exact end overlap, partial overlap, enclosing overlap, interior overlap, back-to-back adjacent slot allowance, cancelled appointment exclusion, concurrent double-booking race condition prevention via row-locking.
- **Foreign Key Safety & Validation (10 tests)**: naive datetime rejection, invalid status transition, FK restrict enforcement on doctor/service/patient deletion with appointments, inactive doctor/patient/service booking rejection.

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

#### Create Patient
```powershell
$patientBody = @{
  full_name = "John Doe"
  phone     = "+91-9876543210"
  email     = "john.doe@example.com"
  gender    = "male"
} | ConvertTo-Json

$patient = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/patients -Headers $headers -ContentType "application/json" -Body $patientBody
```

#### Query Available Slots
```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/appointments/available-slots?doctor_id=$($doctor.id)&service_id=$($service.id)&date=2026-10-05" -Headers $headers
```

#### Book Appointment
```powershell
$apptBody = @{
  patient_id = $patient.id
  doctor_id  = $doctor.id
  service_id = $service.id
  start_at   = "2026-10-05T10:00:00+05:30"
  reason     = "Cardiology Consultation"
} | ConvertTo-Json

$appt = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/appointments -Headers $headers -ContentType "application/json" -Body $apptBody
```

#### Cancel Appointment
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/appointments/$($appt.id)/cancel" -Headers $headers
```

### 4. Interactive OpenAPI Docs

Visit [http://localhost:8000/docs](http://localhost:8000/docs) in your browser. The "Authorize" button supports testing protected endpoints via Bearer token.

---

## Project Structure (Phase 4)

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
    │       ├── 02dc00970591_create_doctors_services_doctor_working_.py
    │       └── 23098df46eaf_create_patients_and_appointments.py
    ├── app/
    │   ├── main.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── appointments.py       # Appointments CRUD, available-slots, cancel, reschedule
    │   │   ├── auth.py               # Register, Login, Me endpoints
    │   │   ├── doctors.py            # Doctors & working hours CRUD endpoints
    │   │   ├── patients.py           # Patients CRUD, search, soft deactivation
    │   │   └── services.py           # Services CRUD endpoints
    │   ├── core/
    │   │   ├── config.py             # App settings (Pydantic)
    │   │   └── security.py           # Argon2 hashing, HS256 JWT, get_current_user
    │   ├── db/
    │   │   ├── base.py               # DeclarativeBase
    │   │   └── session.py            # Async engine & sessionmaker
    │   ├── models/
    │   │   ├── __init__.py           # UserRole, AppointmentStatus enums
    │   │   ├── appointment.py        # Appointment model (RESTRICT FKs, status, start/end)
    │   │   ├── clinic.py             # Clinic model (timezone, has many patients/appts)
    │   │   ├── doctor.py             # Doctor model (clinic FK, appointments passive_deletes)
    │   │   ├── doctor_working_hour.py # DoctorWorkingHour model (clinic & doctor FK)
    │   │   ├── patient.py            # Patient model (clinic FK, unique phone per clinic)
    │   │   ├── service.py            # Service model (clinic FK, duration, price)
    │   │   └── user.py               # User model (clinic FK, role, hash)
    │   ├── schemas/
    │   │   ├── __init__.py
    │   │   ├── appointment.py        # Appointment create, update, response, slot schemas
    │   │   ├── auth.py               # Auth request & response schemas
    │   │   ├── doctor.py             # Doctor create, update, response schemas
    │   │   ├── patient.py            # Patient create, update, response schemas
    │   │   ├── service.py            # Service create, update, response schemas
    │   │   └── working_hour.py       # Working hour create, update, response schemas
    │   └── services/
    │       ├── __init__.py
    │       ├── appointment_service.py # Appointment booking, conflict check, with_for_update locking
    │       ├── auth_service.py       # Auth business logic
    │       ├── availability_service.py # Available slot calculation across shifts & timezone
    │       ├── doctor_service.py     # Doctor business logic & FK conflict handling
    │       ├── patient_service.py    # Patient CRUD, search, soft deactivation
    │       ├── service_service.py    # Service business logic & FK conflict handling
    │       └── working_hour_service.py # Working hour business logic & validation
    └── tests/
        ├── conftest.py               # Async test fixtures, separate DB, NullPool
        ├── test_auth.py              # 16 authentication & tenant tests
        ├── test_clinic_config.py     # 34 clinic configuration tests
        └── test_patients_appointments.py # 57 patients, appointments, availability & concurrency tests
```
