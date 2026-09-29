# AI Patient Front Desk

Multi-tenant SaaS application for clinic patient communication via WhatsApp.

> **Current status: Phase 1 — Project Foundation**
>
> FastAPI application connected to PostgreSQL with Alembic migration framework.
> No models, authentication, business logic, or AI functionality yet.

---

## What Works in Phase 1

- FastAPI application starts and serves requests
- PostgreSQL connection via async SQLAlchemy
- Health endpoint verifying database connectivity
- Alembic migration framework initialized (no revisions yet)
- OpenAPI documentation auto-generated at `/docs`

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 17** (installed and running as a Windows service)
- **Git**

---

## Setup Instructions

### 1. Create the Database

Open a terminal and connect to your local PostgreSQL server using `psql`:

**Windows PowerShell:**

```powershell
psql -U postgres
```

Enter your PostgreSQL password when prompted. Then create the database:

```sql
CREATE DATABASE ai_patient_frontdesk;
```

Verify it was created:

```sql
\l
```

You should see `ai_patient_frontdesk` in the list. Exit `psql`:

```sql
\q
```

> If `psql` is not on your PATH, find it at
> `C:\Program Files\PostgreSQL\17\bin\psql.exe` (typical default installation path).

### 2. Create a Python Virtual Environment

**Windows PowerShell:**

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> If you get an execution policy error, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Linux / macOS:**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Now edit `.env` and replace `YOUR_PASSWORD` with your actual PostgreSQL password:

```
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/ai_patient_frontdesk
```

### 5. Start the Application

```bash
uvicorn app.main:app --reload --port 8000
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## Verification

### Health Endpoint

**Windows PowerShell:**

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

**Linux / macOS:**

```bash
curl http://localhost:8000/api/v1/health
```

**Expected response:**

```json
{
  "status": "healthy",
  "database": "connected",
  "version": "0.1.0"
}
```

### OpenAPI Documentation

Open in browser: [http://localhost:8000/docs](http://localhost:8000/docs)

### Alembic Verification

From the `backend/` directory (with venv activated):

```bash
alembic current
```

Expected output: empty (no migrations exist yet — models are introduced in Phase 2).

```bash
alembic heads
```

Expected output: empty (no revisions).

This confirms Alembic can connect to the database and is properly configured.

---

## Project Structure (Phase 1)

```
AI Patient Front Desk/
├── docker-compose.yml          # Available for future phases (not required now)
├── README.md
├── .gitignore
└── backend/
    ├── .env.example            # Environment variable template
    ├── requirements.txt        # Python dependencies
    ├── Dockerfile              # Container build (future use)
    ├── alembic.ini             # Alembic configuration
    ├── alembic/
    │   ├── env.py              # Async migration environment
    │   ├── script.py.mako      # Migration script template
    │   └── versions/           # Migration revisions (empty)
    └── app/
        ├── __init__.py
        ├── main.py             # FastAPI application + health endpoint
        ├── core/
        │   ├── __init__.py
        │   └── config.py       # Pydantic settings from .env
        └── db/
            ├── __init__.py
            ├── base.py         # SQLAlchemy DeclarativeBase
            └── session.py      # Async engine + session factory
```

---

## Troubleshooting

### "Connection refused" on health check

- Verify PostgreSQL is running: open **Services** (`services.msc`) and check that the PostgreSQL service status is **Running**.
- Verify the `DATABASE_URL` in `.env` has the correct password.
- Verify the `ai_patient_frontdesk` database exists by connecting with `psql -U postgres -l`.

### Alembic import errors or connection failures

- Ensure you're running `alembic` from the `backend/` directory.
- Ensure your virtual environment is activated.
- Ensure `.env` file exists in `backend/` with the correct `DATABASE_URL`.

### `psql` is not recognized

Add PostgreSQL bin directory to your PATH:

```powershell
$env:PATH += ";C:\Program Files\PostgreSQL\17\bin"
```

Or use the full path:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres
```

### `uvicorn` not found

Ensure the virtual environment is activated:

```powershell
.\venv\Scripts\Activate.ps1
```

Your prompt should show `(venv)` prefix.

### `Activate.ps1 cannot be loaded`

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Next Phase

**Phase 2: Authentication & Multi-tenancy** — User registration, login, JWT, clinic creation, tenant isolation.

Do not proceed until Phase 1 is confirmed working.
