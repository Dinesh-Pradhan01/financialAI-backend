import asyncio
from app.upload_engine.services.upload_engine import UploadEngine
from app.db.session import AsyncSessionLocal

async def run():
    engine = UploadEngine("client")
    async with AsyncSessionLocal() as db:
        res = await engine.process_manual([{"client_id": "1", "status": "Active", "rowId": "row-2", "sourceRow": 2}], db)
        print(res)

if __name__ == "__main__":
    asyncio.run(run())
