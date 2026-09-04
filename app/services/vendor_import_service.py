from sqlalchemy.ext.asyncio import AsyncSession
from app.upload_engine.importer.bulk_importer import BulkImporter
from app.schemas.vendor import VendorPreview

async def import_vendors(preview_data: VendorPreview, db: AsyncSession, imported_by: str = "system") -> dict:
    valid_records = []
    error_row_ids = set(preview_data.summary.get("errorRowIds", []))
    
    for record in preview_data.records:
        if record.model_dump().get("rowId") not in error_row_ids and not record.model_dump().get("isBlank"):
            valid_records.append(record.model_dump())
            
    return await BulkImporter.import_data("vendor", preview_data.upload_id, valid_records, db, imported_by)
