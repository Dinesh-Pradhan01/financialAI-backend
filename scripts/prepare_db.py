"""
One-time script to prepare the database for the fresh auth migration.
Drops the existing `users` table (which has the old schema) and
clears the alembic_version table so we can run migrations from scratch.
Does NOT touch other tables (persons, documents, etc.).
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    # Check existing tables
    result = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ))
    tables = [row[0] for row in result]
    print("Existing tables:", tables)

    # Drop old users table (old schema, will be recreated by migration)
    if "users" in tables:
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        print("Dropped old 'users' table.")

    # Drop sessions if it exists (shouldn't, but just in case)
    if "sessions" in tables:
        conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE"))
        print("Dropped old 'sessions' table.")

    # Clear alembic version history
    if "alembic_version" in tables:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
        print("Dropped 'alembic_version' table.")

    print("Database ready for fresh migration.")

engine.dispose()
