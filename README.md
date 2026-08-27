# Spotlite Backend API

This is the backend API for the Spotlite Financial Analysis platform. It is built using **FastAPI**, **SQLAlchemy** (async), **PostgreSQL**, **Firebase Admin SDK** (for auth verification), and **Google Gemini** (for AI-powered document processing).

---

## Key Features & APIs

- **Authentication & Sessions**: Syncs with Firebase JWTs, establishes secure session cookies, and maintains user context.
- **User Profiles**: Profiles CRUD management for users and associated entities.
- **Industry & Stock Insights**: 
  - `/v1/basic-industry/{basic_industry_name}`: Returns quarterly peer financial metrics, scaled MSME benchmark financials, and growth trends.
  - `/v1/stocks/top5`: Fetches daily price charts for top 5 stocks within a basic industry (accepts query parameter `basic_industry`, e.g., `/v1/stocks/top5?basic_industry=2/3 Wheelers`).
- **Bank Statement Analyzer**: Asynchronous, AI-driven bank statement text extraction, categorization, validation, and metadata parsing using Google Gemini.

---

## Technical Stack & Libraries

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous endpoints, automatic OpenAPI docs)
- **Database ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async extension)
- **Driver**: `asyncpg` (PostgreSQL driver)
- **Database Migrations**: [Alembic](https://alembic.otierney.net/)
- **Authentication**: Firebase Admin SDK (token verification and verification flow syncing)
- **AI Engine**: Google GenAI SDK (utilizing `gemini-2.5-flash` or similar models)
- **File Upload**: `python-multipart`

---

## Directory Layout

```text
financialAI-backend/
├── app/
│   ├── auth/                # Session cookies, Firebase verification, user synchronization
│   │   ├── dependencies.py  # Dependency injection for user authentication
│   │   ├── firebase.py      # Initialize and verify Firebase JWTs
│   │   ├── model.py         # SQLAlchemy & Pydantic models for authentication
│   │   ├── routes.py        # Authentication API router endpoints (/auth/sync, /auth/me, /auth/logout)
│   │   └── service.py       # Session management logic and user upsert helpers
│   ├── database/            # Connection establishment & base schemas
│   │   ├── connection.py    # Async session maker, engine setup, database seeding
│   │   ├── models.py        # Core entity declarations (Base, TimestampMixin, Person)
│   │   └── repository.py    # Database query abstractions
│   ├── industry/            # Industry & Stock Analysis
│   │   └── routes.py        # Peer average comparison & Top 5 stock list endpoints
│   ├── person/              # User Profile Management
│   │   └── routes.py        # Profile crud router endpoints (/persons/me)
│   ├── statement/           # Bank Statement Parsing & Analysis
│   │   └── ...              # AI parsing, entity extraction, statement analysis routers
│   └── config.py            # Pydantic Settings configuration load
├── alembic/                 # Alembic configuration and migration versions
├── main.py                  # API App instantiation, middleware declarations, CORS, routing
├── requirements.txt         # Pip packages definition
└── firebase-service-account.json # Secret Firebase credential JSON (GIT IGNORED)
```

---

## Setup & Running Guide

### 1. Prerequisites

- Python 3.10 or higher installed.
- PostgreSQL database running locally or in the cloud (e.g. Neon).

### 2. Installation

1. Create a virtual environment named `spot`:
   ```bash
   python -m venv spot
   ```
2. Activate the virtual environment:
   * **Windows (PowerShell)**:
     ```powershell
     .\spot\Scripts\Activate.ps1
     ```
   * **macOS/Linux**:
     ```bash
     source spot/bin/activate
     ```
3. Install package requirements:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Environment Configuration

Create a `.env` file in the `financialAI-backend` root folder. Populate it with variables like so:

```ini
APP_NAME="Spotlite Backend API"
DEBUG=true

# PostgreSQL URL
DATABASE_URL="postgresql://user:password@host:port/dbname?sslmode=require"

# Gemini AI Studio Key
GEMINI_API_KEY="AIzaSy..."

# Firebase Admin SDK Configuration
FIREBASE_PROJECT_ID="your-project-id"
FIREBASE_CREDENTIALS_PATH="./firebase-service-account.json"

# CORS configuration (comma separated list of origins)
CORS_ORIGINS="http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080"
FRONTEND_URL="http://localhost:8080"
```

> [!IMPORTANT]
> Make sure to place your downloaded Firebase service account JSON file in the root of the backend directory with the filename `firebase-service-account.json`. Do **not** commit this file to git (it is ignored by `.gitignore`).

### 4. Running the Dev Server

Start the application with Uvicorn:
```bash
uvicorn main:app --reload
```

- **OpenAPI / Swagger UI docs**: Visit `http://127.0.0.1:8000/docs`
- **ReDoc API docs**: Visit `http://127.0.0.1:8000/redoc`

---

## Database Migrations

This project uses **Alembic** to manage changes in the database.

- **Create a migration**:
  ```bash
  alembic revision --autogenerate -m "migration description"
  ```
- **Apply migrations**:
  ```bash
  alembic upgrade head
  ```
- **Downgrade migrations**:
  ```bash
  alembic downgrade -1
  ```
