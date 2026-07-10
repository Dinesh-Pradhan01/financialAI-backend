# Spotlite — Firebase Authentication Setup

This document covers setup instructions for the Firebase Authentication integration.

## Architecture Overview

```
┌──────────────┐       Firebase ID Token        ┌──────────────────┐
│   Frontend   │  ──────────────────────────────▶│   FastAPI        │
│   (React)    │        Authorization:           │   Backend        │
│              │        Bearer <token>           │                  │
│  Firebase JS │                                 │  Firebase Admin  │
│  SDK v12     │◀─── JSON responses ────────────│  SDK v6          │
└──────────────┘                                 └──────────────────┘
       │                                                │
       │  Sign up / Login                               │  Verify token
       ▼                                                │  Sync user
┌──────────────┐                                        ▼
│   Firebase   │                                 ┌──────────────────┐
│   Auth       │                                 │  NeonDB          │
│  (Identity   │                                 │  PostgreSQL      │
│   Provider)  │                                 │  (users table)   │
└──────────────┘                                 └──────────────────┘
```

**Key principle**: Firebase is the *identity provider* only. All authorization decisions (roles, permissions) are made by the FastAPI backend using the `users` PostgreSQL table via SQLAlchemy 2.0.

---

## Prerequisites

1. A Firebase project with **Email/Password** authentication enabled
2. Python 3.10+
3. Node.js / Bun
4. A NeonDB PostgreSQL database (or any PostgreSQL instance)

---

## Environment Variables

### Frontend (`financialAI-frontend/.env.local`)

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_FIREBASE_API_KEY` | Firebase Web API Key | `AIzaSy...` |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase Auth Domain | `myproject.firebaseapp.com` |
| `VITE_FIREBASE_PROJECT_ID` | Firebase Project ID | `myproject-12345` |
| `VITE_FIREBASE_APP_ID` | Firebase App ID | `1:123456:web:abcdef` |
| `VITE_API_BASE_URL` | Backend API base URL | `http://localhost:8000` |

### Backend (`financialAI-backend/.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | `postgresql+asyncpg://user:pass@host/db?ssl=require` |
| `FIREBASE_PROJECT_ID` | Firebase Project ID | `myproject-12345` |
| `FIREBASE_CREDENTIALS_PATH` | Path to service account JSON | `./firebase-service-account.json` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000,http://localhost:5173` |
| `FRONTEND_URL` | Frontend URL for redirects | `http://localhost:3000` |

> **NeonDB Connection String**: Copy your connection string from the NeonDB dashboard.
> Prefix it with `postgresql+asyncpg://` (replace `postgres://` or `postgresql://`).
> Ensure `?ssl=require` or `?sslmode=require` is appended.

---

## Setup Instructions

### 1. Firebase Console Setup

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (or create one)
3. Navigate to **Authentication** → **Sign-in method**
4. Enable **Email/Password** provider
5. Navigate to **Project Settings** → **Service Accounts**
6. Click **Generate new private key**
7. Save the JSON file as `firebase-service-account.json` in the `financialAI-backend/` directory

> ⚠️ **Never commit this file to version control.** It is already in `.gitignore`.

### 2. Backend Setup

```bash
cd financialAI-backend

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Edit .env — set DATABASE_URL to your NeonDB connection string:
# DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/neondb?ssl=require

# Start the backend (tables are auto-created on startup)
uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd financialAI-frontend

# Install dependencies
bun install

# Configure environment
# Edit .env.local with your Firebase project details

# Start the dev server
bun run dev
```

---

## Database Schema

The backend uses **SQLAlchemy 2.0** with async sessions (`asyncpg` driver) to interact with NeonDB PostgreSQL.

### `users` Table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `INTEGER` | PK, auto-increment | Internal user ID |
| `firebase_uid` | `VARCHAR(128)` | UNIQUE, indexed | Firebase Authentication UID |
| `email` | `VARCHAR(320)` | NOT NULL | Email from Firebase |
| `role` | `VARCHAR(20)` | NOT NULL, default `"user"` | Application role |
| `is_active` | `BOOLEAN` | NOT NULL, default `true` | Soft-delete flag |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, server default `now()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, server default `now()` | Last update timestamp |

Tables are **auto-created** on application startup via `Base.metadata.create_all()`.

---

## API Endpoints

### Authentication

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/auth/sync` | ✅ Bearer Token | Sync Firebase user to local DB (call after first login) |
| `GET` | `/auth/me` | ✅ Bearer Token | Get current user profile |

### Health

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `GET` | `/` | ❌ | Root endpoint |
| `GET` | `/health` | ❌ | Health check (DB connectivity via `SELECT 1`) |

### Making Authenticated Requests

Every authenticated request must include the Firebase ID token:

```
Authorization: Bearer <firebase_id_token>
```

The frontend API client (`src/lib/api.ts`) handles this automatically.

---

## User Model

### Roles

| Role | Description |
|------|-------------|
| `user` | Default role assigned on first login |
| `admin` | Administrative access — must be assigned manually in the database |

### Assigning Admin Role

```python
# In a Python shell or management script:
import asyncio
from sqlalchemy import update
from app.database.connection import async_session_factory
from app.auth.model import User

async def make_admin(firebase_uid: str):
    async with async_session_factory() as session:
        stmt = update(User).where(
            User.firebase_uid == firebase_uid
        ).values(role="admin")
        await session.execute(stmt)
        await session.commit()

asyncio.run(make_admin("firebase_uid_here"))
```

Or directly via SQL in the NeonDB console:

```sql
UPDATE users SET role = 'admin' WHERE firebase_uid = 'firebase_uid_here';
```

---

## RBAC Usage

To protect endpoints with role-based access:

```python
from fastapi import Depends
from app.auth.dependencies import get_current_user, require_role

# Any authenticated user
@router.get("/profile")
async def get_profile(user = Depends(get_current_user)):
    return {"email": user.email}

# Admin only
@router.get("/admin/users")
async def list_all_users(user = Depends(require_role("admin"))):
    ...

# Multiple roles
@router.delete("/data/{id}")
async def delete_data(id: str, user = Depends(require_role("admin", "moderator"))):
    ...
```

---

## Security Checklist

- [x] Firebase ID tokens verified on every request (signature + expiry + revocation)
- [x] Email verification enforced before accessing protected resources
- [x] Tokens stored in memory only (no localStorage)
- [x] Automatic token refresh via Firebase JS SDK
- [x] CORS configured with explicit allowed origins
- [x] Service account JSON excluded from version control
- [x] No hardcoded credentials in source code
- [x] RBAC controlled by backend database, not Firebase custom claims
- [x] Deactivated users rejected at the dependency level
- [x] Principle of least privilege: default role is "user"
- [x] NeonDB connection uses SSL (`?ssl=require`)

---

## Testing Checklist

1. **Signup**: Create account → verification email received → user exists in Firebase
2. **Verify Email**: Click verification link → emailVerified updates → redirect to home
3. **Login**: Sign in with verified email → token obtained → home page loads
4. **Unverified Login**: Sign in without verification → redirect to verify-email page
5. **Auth Guard**: Access `/home` while logged out → redirect to `/login`
6. **Backend Sync**: After first login → user row created in PostgreSQL `users` table
7. **GET /auth/me**: Returns correct user profile with valid token
8. **Invalid Token**: Call `/auth/me` with bad token → 401 response
9. **Expired Token**: Wait for token to expire → auto-refresh on next API call
10. **RBAC**: Regular user calls admin endpoint → 403 response
11. **Logout**: Sign out → token cleared → redirect to login → cannot access protected routes
12. **Password Reset**: Click "Forgot password" → reset email received → can set new password
13. **CORS**: Frontend can call backend API → no CORS errors in console
14. **Health Check**: `GET /health` returns `{"status": "healthy", "database": "connected"}`
