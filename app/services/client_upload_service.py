from typing import Dict, Any, List, Optional
import uuid
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.upload_engine.services.upload_engine import UploadEngine

async def process_client_excel_upload(file: UploadFile, db: AsyncSession, uploaded_by: str = "system", business_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    engine = UploadEngine(module_name="client")
    return await engine.process_file(file, db, uploaded_by, business_id)

async def process_client_manual_entry(data: List[Dict[str, Any]], db: AsyncSession, uploaded_by: str = "system", business_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    engine = UploadEngine(module_name="client")
    return await engine.process_manual(data, db, uploaded_by, business_id)
