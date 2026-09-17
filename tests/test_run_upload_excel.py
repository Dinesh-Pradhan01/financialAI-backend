import asyncio
from app.upload_engine.services.upload_engine import UploadEngine
from app.db.session import AsyncSessionLocal
import openpyxl
import io
from fastapi import UploadFile

async def run():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["client_id", "client_name", "status", "contract_value", "ifsc_code"])
    ws.append(["C-001", "Acme", "Active", "", ""])
    
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    file = UploadFile(filename="test.xlsx", file=buf)
    
    engine = UploadEngine("client")
    async with AsyncSessionLocal() as db:
        res = await engine.process_file(file, db, uploaded_by="system")
        print(res["records"])

if __name__ == "__main__":
    asyncio.run(run())
