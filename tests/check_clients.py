import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import select, func
from app.db.models.client import ClientMaster

async def check_clients():
    async with AsyncSessionLocal() as db:
        stmt = select(func.count(ClientMaster.id))
        result = await db.execute(stmt)
        count = result.scalar()
        
        print(f"Total clients in DB: {count}")
        
        if count > 0:
            stmt2 = select(ClientMaster).limit(5)
            res = await db.execute(stmt2)
            for c in res.scalars().all():
                print(f"Client ID: {c.client_id}, Name: {c.client_name}, Revenue: {c.revenue}")

if __name__ == "__main__":
    asyncio.run(check_clients())
