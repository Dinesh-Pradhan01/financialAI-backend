import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.auth.model import User
from app.database.connection import DATABASE_URL

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        stmt = select(User).where(User.email == 'dineshpradhan.byteiq@gmail.com')
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        print('Email verified:', user.email_verified if user else 'Not found')

if __name__ == '__main__':
    asyncio.run(main())
