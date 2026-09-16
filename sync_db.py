import asyncio
from app.database.connection import init_db

async def main():
    print("Running init_db() to sync new MSME categories...")
    await init_db()
    print("Database sync complete.")

if __name__ == "__main__":
    asyncio.run(main())
