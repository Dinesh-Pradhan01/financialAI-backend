# Spotlite Backend API

This is the backend API for the **Spotlite** platform. Built using **FastAPI** (asynchronous), **SQLAlchemy 2.0**, **PostgreSQL**, **Firebase Admin SDK** (for identity verification and session syncing), **Google Gemini AI** (for document processing and business analysis), **SendGrid** (for asynchronous email notifications), and an **Excel/CSV Upload Engine** (for bulk HR and Vendor data importing).

---

## 🌟 Key Features

- **Asynchronous AI Bank Statement Analyzer**: Bulk or single PDF uploads with MD5 deduplication. Extracts accounts, parses transaction lists, categorizes expenses, and logs processing telemetry using the Google GenAI SDK (`gemini-2.5-flash`).
- **HR & Vendor Upload Engine**: Imports employee master and vendor master data from Excel/CSV sheets. Supports schema validation, custom business rule validation, automatic duplicate checks, preview building, and comprehensive import logs.
- **Identity & Session Management**: Syncs Firebase Authentication tokens, manages secure HTTP-only cookies (`session`), manages session lifetime, and provides Role-Based Access Control (RBAC).
- **Business Onboarding Pipeline**: A multi-step flow (General info, Leadership profiles, Financial details, Document uploads) with automated AI verification document parsing.
- **Team Invitations & Revocation**: CEO/Admin roles can invite team members (`cfo` or `hr`) via SendGrid-notified tokenized links, revoke invitations, or remove members (which invalidates active backend sessions and revokes Firebase refresh tokens).
- **Company & Document Analytics**: Manages company profiles, industry leaders, rating indexes, and RSS financial news feeds. Integrates AI-generated executive summaries and packages management.
- **Industry & Stock Insights**: Fetches daily stock price charts for top 5 stocks and returns scaled MSME benchmark financials and averages.

---

## 🛠️ Technical Stack & Libraries

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous operations, lifespan management, custom OpenAPI/Swagger patches for file uploads)
- **Database ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async extension) with `asyncpg` driver for PostgreSQL
- **AI Processing**: Google Generative AI (`google-generativeai`)
- **Identity Provider**: [Firebase Admin SDK](https://firebase.google.com/docs/admin) (JWT verification and session cookie verification)
- **Emails**: SendGrid API client (`sendgrid`)
- **Data Import**: Pandas and OpenPyXL (for parsing Excel and CSV files)
- **Migrations**: Alembic
- **Template Rendering**: Jinja2 (for HTML email templates)

---

## 📁 Directory Layout

```text
financialAI-backend/
├── app/
│   ├── ai/                  # AI utilities (LLM integration, prompts, structured output parsing)
│   │   ├── llm.py           # Gemini SDK interface & structured JSON queries
│   │   └── prompts.py       # Prompt templates for bank statements & business documents
│   ├── auth/                # Session cookies, Firebase verification, user synchronization
│   │   ├── dependencies.py  # Dependency injection for user auth, sessions, and RBAC
│   │   ├── firebase.py      # Initialize and verify Firebase JWTs
│   │   ├── model.py         # SQLAlchemy & Pydantic models for auth & roles
│   │   ├── routes.py        # Auth & manual invites (/auth/sync, /auth/me, /auth/invite)
│   │   └── service.py       # Session management logic and user upsert helpers
│   ├── business/            # Business Profiles & Onboarding
│   │   ├── invite_routes.py # Invitation verification & acceptance routes
│   │   ├── invite_service.py# Link builders, tokenization, & invite audit logs
│   │   ├── models.py        # GeneralInfo, LeadershipInfo models
│   │   └── routes.py        # Multi-step business onboarding & document upload
│   ├── company/             # Company details, PDF documents & Packages
│   │   ├── document_routes.py# Company document uploads & client package setup
│   │   ├── models.py        # CompanyProfile, Document, Package schemas
│   │   └── routes.py        # Rating, News (RSS), and Gemini-powered AI views
│   ├── core/                # Core configurations & logging
│   │   ├── config.py        # Pydantic settings schema for HR module
│   │   └── logging.py       # Logger settings
│   ├── database/            # Database configurations & connection pools
│   │   ├── connection.py    # Async engine, session makers, auto schema column sync
│   │   ├── models.py        # Base, TimestampMixin, Accounts, Transactions, Documents
│   │   └── repository.py    # Database query abstract CRUD repository
│   ├── db/                  # HR/Vendor Database Models and base class
│   │   ├── base.py          # Declarative Base, Mixins
│   │   └── models/          # employee, vendor, upload database models
│   ├── email_service/       # SendGrid email dispatcher
│   │   ├── service.py       # SendGrid client and template loader
│   │   └── templates/       # HTML email templates (invitation, alert)
│   ├── industry/            # Industry analytics & Stock charts
│   │   └── routes.py        # Peer comparisons, MSME benchmarks, stock chart data
│   ├── person/              # User profile details
│   │   └── routes.py        # Personal profiles CRUD endpoints
│   ├── statement/           # Bank Statement Parsing & Analysis
│   │   ├── review/          # PDF file validation, MD5 hashing, duplicate detection
│   │   └── upload/          # Main single/bulk parser upload routes
│   ├── storage/             # File storage managers
│   │   └── file_manager.py  # Local directory creation and file storage adapters
│   ├── upload_engine/       # HR & Vendor bulk excel/csv parser and validation engine
│   └── config.py            # Pydantic Settings configuration load from .env
│   └── main.py              # Main FastAPI application routes and setup
├── alembic/                 # Alembic migrations configuration and versions
├── main.py                  # API App entry point, CORS configuration, Lifespan hooks
├── requirements.txt         # Python package dependencies
└── firebase-service-account.json # Secret Firebase credential JSON (GIT IGNORED)
```

---

## 🚀 Setup & Execution Guide

### 1. Prerequisites
- **Python**: version `3.10` or higher.
- **PostgreSQL**: Local instance or cloud hosted (e.g. Neon DB).
- **Firebase**: A Firebase project with **Email/Password** authentication enabled.
- **SendGrid**: An API Key with verification sender email configured.

### 2. Environment Settings
Create a `.env` file in the root of the `financialAI-backend/` folder:

```ini
APP_NAME="Spotlite Backend API"
DEBUG=true

# Database Connection (Neon PostgreSQL asyncpg)
DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"

# Gemini AI Studio Key
GEMINI_API_KEY="AIzaSy..."

# Firebase Credentials
FIREBASE_PROJECT_ID="your-firebase-project-id"
FIREBASE_CREDENTIALS_PATH="./firebase-service-account.json"

# CORS configuration (comma separated list of origins)
CORS_ORIGINS="http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080"
FRONTEND_URL="http://localhost:8080"

# SendGrid Email Credentials
SENDGRID_API_KEY="SG.xxx..."
SENDER_EMAIL="your-registered-sender@domain.com"
```

> [!IMPORTANT]
> Download your Firebase Service Account Private Key JSON from **Firebase Console** -> **Project Settings** -> **Service Accounts**. Rename it to `firebase-service-account.json` and save it directly in the root of `financialAI-backend/`. Do **not** commit this file to Git.

### 3. Installation & Run
1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # macOS / Linux
   source venv/bin/activate
   ```
2. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   uvicorn main:app --reload
   ```

* **Interactive API Documentation (Swagger)**: Visit `http://127.0.0.1:8000/docs`
* **Alternate API Documentation (ReDoc)**: Visit `http://127.0.0.1:8000/redoc`

---

## 🗄️ Database Schema & Migrations

### Database Migrations (Alembic)
If you make changes to the SQLAlchemy models, you can run Alembic migrations:
- **Create an autogenerated migration**:
  ```bash
  alembic revision --autogenerate -m "migration description"
  ```
- **Apply migrations to database**:
  ```bash
  alembic upgrade head
  ```
- **Downgrade migrations by 1**:
  ```bash
  alembic downgrade -1
  ```
