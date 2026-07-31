import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database.connection import db_manager

async def clean_db():
    try:
        async with db_manager.engine.begin() as conn:
            await conn.execute(text("""
                DROP TABLE IF EXISTS 
                  business_info, 
                  business_financial_info, 
                  business_verifications, 
                  business_documents, 
                  business_general_info, 
                  general_info, 
                  leadership_info, 
                  financial_info 
                CASCADE;
            """))
        print("Successfully dropped all old and new business tables!")
    except Exception as e:
        print(f"Error dropping tables: {e}")
    finally:
        await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(clean_db())
