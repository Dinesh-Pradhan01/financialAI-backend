import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.database.connection import DATABASE_URL

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN founder_ceo_email VARCHAR(255);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN founder_ceo_phone VARCHAR(20);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN cfo_phone VARCHAR(20);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN cfo_designation VARCHAR(100);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN invite_cfo BOOLEAN DEFAULT FALSE;"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN hr_phone VARCHAR(20);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN hr_designation VARCHAR(100);"))
        except Exception as e: print(e)
        try:
            await conn.execute(text("ALTER TABLE leadership_info ADD COLUMN invite_hr BOOLEAN DEFAULT FALSE;"))
        except Exception as e: print(e)
        
    print("DB migration completed.")

if __name__ == '__main__':
    asyncio.run(main())
