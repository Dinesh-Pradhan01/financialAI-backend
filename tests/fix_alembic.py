import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def fix_alembic():
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE alembic_version SET version_num = 'f891024_vendor_composite_pk'"))
        await db.commit()
        print("Updated alembic_version to f891024_vendor_composite_pk")

if __name__ == "__main__":
    asyncio.run(fix_alembic())
