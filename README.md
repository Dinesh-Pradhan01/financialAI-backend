# Spotlite HR & Client Management Platform - Backend

This is the backend foundation for the Spotlite platform. It is built using FastAPI, PostgreSQL (via asyncpg), and SQLAlchemy 2.x.

## Setup Instructions

1. **Environment Setup**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuration**
   Copy `.env.example` to `.env` and fill in the PostgreSQL credentials.
   ```bash
   cp .env.example .env
   ```

3. **Running the Application**
   ```bash
   uvicorn app.main:app --reload
   ```

The server will start at `http://localhost:8000`.
Health check endpoint is available at `/health`.
