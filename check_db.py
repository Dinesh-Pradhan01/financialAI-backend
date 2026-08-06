import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.database.models import Person
from app.database.connection import DATABASE_URL

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        stmt = select(Person).where(Person.email == 'dineshpradhan.byteiq@gmail.com')
        res = await session.execute(stmt)
        person = res.scalar_one_or_none()
        print('Profile completed:', person.profile_completed if person else 'Not found')

if __name__ == '__main__':
    asyncio.run(main())
