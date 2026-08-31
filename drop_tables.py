import asyncio
from app.db.session import engine
from sqlalchemy import text

async def drop_alembic():
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    print("Alembic dropped.")

if __name__ == "__main__":
    asyncio.run(drop_alembic())
