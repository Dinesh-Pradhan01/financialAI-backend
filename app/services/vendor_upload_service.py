from typing import Dict, Any, List
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.upload_engine.services.upload_engine import UploadEngine

async def process_vendor_excel_upload(file: UploadFile, db: AsyncSession, uploaded_by: str = "system") -> Dict[str, Any]:
    engine = UploadEngine(module_name="vendor")
    return await engine.process_file(file, db, uploaded_by)

async def process_vendor_manual_entry(data: List[Dict[str, Any]], db: AsyncSession, uploaded_by: str = "system") -> Dict[str, Any]:
    engine = UploadEngine(module_name="vendor")
    return await engine.process_manual(data, db, uploaded_by)
