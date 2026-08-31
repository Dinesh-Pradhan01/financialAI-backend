# Spotlite Backend API

This is the backend API for the **Spotlite Financial Analysis** platform. Built using **FastAPI** (asynchronous), **SQLAlchemy 2.0**, **PostgreSQL**, **Firebase Admin SDK** (for identity verification and session syncing), **Google Gemini AI** (for document processing and business analysis), and **SendGrid** (for asynchronous email notifications).

---

## 🌟 Key Features

- **Asynchronous AI Bank Statement Analyzer**: Bulk or single PDF uploads with MD5 deduplication. Extracts accounts, parses transaction lists, categorizes expenses, and logs processing telemetry using the Google GenAI SDK (`gemini-2.5-flash`).
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
│   ├── database/            # Database configurations & connection pools
│   │   ├── connection.py    # Async engine, session makers, auto schema column sync
│   │   ├── models.py        # Base, TimestampMixin, Accounts, Transactions, Documents
│   │   └── repository.py    # Database query abstract CRUD repository
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
│   └── config.py            # Pydantic Settings configuration load from .env
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
   python -m venv spot
   # Windows (PowerShell)
   .\spot\Scripts\Activate.ps1
   # macOS / Linux
   source spot/bin/activate
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

## 🗄️ Database Schema & Roles Auto-Seeding

On application startup, `app.database.connection.init_db()` is automatically invoked. This routine:
1. Verifies/Creates all tables (`Base.metadata.create_all`).
2. Checks and runs database column-level updates dynamically.
3. Automatically seeds the roles table with default values (`ceo`, `cfo`, `hr`, `admin`) if they are missing.

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

---

## 📡 API Endpoints Reference

### 1. Authentication & Team Management (`/api/auth`)
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/sync` | Firebase Token | Syncs Firebase user to local DB, establishes cookies, returns profile completion status |
| `POST` | `/api/auth/google` | Google Payload | Verifies Google Auth token, registers/syncs user, sets session cookie |
| `GET` | `/api/auth/me` | Session Cookie | Returns current user profile, organization ID, and role |
| `POST` | `/api/auth/logout` | Session Cookie | Clears session cookie and invalidates token session in Postgres |
| `POST` | `/api/auth/invite` | Session Cookie (CEO/Admin) | Sends team invite to CFO/HR email using SendGrid template |
| `GET` | `/api/auth/invites` | Session Cookie (CEO/Admin) | Returns list of sent invitations and their verification statuses |
| `DELETE` | `/api/auth/invite/{invite_id}` | Session Cookie (CEO/Admin) | Revokes a pending or expired invitation |
| `POST` | `/api/auth/invite/{invite_id}/remove` | Session Cookie (CEO/Admin) | Removes a member, resets role, revokes all cookies & Firebase refresh tokens |
| `POST` | `/api/auth/invite/{invite_id}/resend` | Session Cookie (CEO/Admin) | Regenerates token and resends invitation email |
| `GET` | `/api/auth/invite/verify/{token}` | None | Verifies validity and 24h expiration of invitation token |
| `POST` | `/api/auth/invite/accept-with-password` | None | Sets password, registers user in database, and generates session cookie |

### 2. Business Onboarding (`/api/business/onboarding` & `/api/invite`)
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/business/onboarding/me` | Session Cookie | Returns full onboarding state of the user's business profile |
| `POST` | `/api/business/onboarding/step/1` | Session Cookie | Saves Step 1: General Business Information (PAN, Type, Category, address) |
| `POST` | `/api/business/onboarding/step/2` | Session Cookie | Saves Step 2: Leadership & Organization details (Founder, CEO info) |
| `POST` | `/api/business/onboarding/step/3` | Session Cookie | Saves Step 3: Financial configuration details |
| `POST` | `/api/business/onboarding/documents/upload` | Session Cookie | Uploads verification files (e.g. GST registration, PAN card, Incorporation certificate) |
| `DELETE` | `/api/business/onboarding/documents/{doc_id}` | Session Cookie | Deletes an uploaded verification document |
| `POST` | `/api/business/onboarding/step/extract-from-docs` | Session Cookie | Runs AI extraction using Gemini on uploaded docs to prefill forms |
| `POST` | `/api/business/onboarding/complete` | Session Cookie | Finalizes onboarding and sets `onboarding_completed` flag to true |
| `GET` | `/api/invite/verify/{token}` | None | Verifies token validation status for onboarding invite |
| `POST` | `/api/invite/accept/{token}` | None | Completes onboarding invite token acceptance |

### 3. Company & Document Packages (`/api/company` & `/api/company/documents`)
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/company/profile` | Session Cookie | Fetches current business company profile metadata |
| `GET` | `/api/company/industry-leaders` | Session Cookie | Retrieves peer averages and lists industry segment leaders |
| `GET` | `/api/company/rating` | Session Cookie | Retrieves the firm's calculated scoring/credit ratings |
| `GET` | `/api/company/news` | Session Cookie | Pulls real-time financial news updates via RSS feed parsing |
| `POST` | `/api/company/ai-view` | Session Cookie | Requests a detailed business analysis outline generated by Gemini |
| `GET` | `/api/company/documents` | Session Cookie | Lists company documents uploaded under the business profile |
| `POST` | `/api/company/documents` | Session Cookie | Uploads a new PDF company document |
| `PUT | `/api/company/documents/{doc_id}` | Session Cookie | Modifies company document metadata |
| `DELETE` | `/api/company/documents/{doc_id}` | Session Cookie | Removes the document from DB and storage |
| `GET` | `/api/company/documents/{doc_id}/download` | Session Cookie | Downloads the document file binary |
| `GET` | `/api/company/packages` | Session Cookie | Lists all document sharing package groups |
| `POST` | `/api/company/packages` | Session Cookie | Creates a new document sharing package configuration |
| `PATCH` | `/api/company/packages/{pkg_id}` | Session Cookie | Edits package metadata details |
| `DELETE` | `/api/company/packages/{pkg_id}` | Session Cookie | Deletes document sharing package |
| `POST` | `/api/company/packages/{pkg_id}/documents` | Session Cookie | Adds a document to the package |
| `DELETE` | `/api/company/packages/{pkg_id}/documents` | Session Cookie | Removes a document from the package |

### 4. Bank Statement Analyzer (`/api/statements`)
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/statements/upload` | Session Cookie | Uploads single bank statement, calculates MD5 hash, enqueues async parsing |
| `POST` | `/api/statements/upload/bulk` | Session Cookie | Uploads list of statement PDFs and parses them in parallel |
| `GET` | `/api/statements` | Session Cookie | Lists all statement uploads for the business (or all for system admins) |
| `GET` | `/api/statements/{id}` | Session Cookie | Fetches the upload metadata and processing status of a statement |
| `GET` | `/api/statements/{id}/status` | Session Cookie | Checks processing stages, performance telemetry, and backend status logs |
| `GET` | `/api/statements/{id}/extracted` | Session Cookie | Retrieves the AI-extracted bank account details and list of transactions |
| `GET` | `/api/statements/{id}/transactions` | Session Cookie | Returns paginated list of transactions parsed from the statement |
| `POST` | `/api/statements/{id}/reprocess` | Session Cookie | Resets status to PENDING and restarts the background processing task |
| `DELETE` | `/api/statements/{id}` | Session Cookie | Deletes statement file locally and cascades deletes account and transaction DB rows |

### 5. Industry Insights (`/api/v1`)
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/basic-industry/{basic_industry_name}` | Session Cookie | Retrieves quarterly peer aggregates, MSME metrics, and growth trends |
| `GET` | `/api/v1/stocks/top5` | Session Cookie | Fetches daily stock price charts for top 5 industry stocks |
| `GET` | `/api/v1/basic-industries` | Session Cookie | Lists configured basic industries |
| `GET` | `/api/v1/classifications` | Session Cookie | Lists basic industry classification options |

### 6. System Health
| Method | Path | Auth Type | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | None | Welcome banner response |
| `GET` | `/health` | None | Performs db query (`SELECT 1`) to check DB engine connection |
