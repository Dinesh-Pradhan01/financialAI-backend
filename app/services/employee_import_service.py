import uuid
from typing import Union, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.employee import EmployeePreviewResponse
from app.services.employee_ingestion_service import EmployeeIngestionService
from app.repositories.upload import upload_history_repository

async def import_employees(preview_data: Union[EmployeePreviewResponse, Dict[str, Any], list], db: AsyncSession, imported_by: str = "system") -> dict:
    if isinstance(preview_data, list):
        p_dict = {"records": preview_data}
    elif isinstance(preview_data, EmployeePreviewResponse):
        p_dict = preview_data.model_dump()
    elif isinstance(preview_data, dict):
        p_dict = preview_data
    else:
        p_dict = {}

    upload_id = p_dict.get("upload_id") or p_dict.get("preview_id")
    records = p_dict.get("records", [])
    if not records and isinstance(preview_data, list):
        records = preview_data

    summary = p_dict.get("summary", {})
    
    error_row_ids = set()
    if isinstance(summary, dict):
        error_row_ids = set(summary.get("errorRowIds", []))
    elif hasattr(summary, "errorRowIds"):
        error_row_ids = set(summary.errorRowIds)

    valid_records = []
    for record in records:
        r_dict = record if isinstance(record, dict) else (record.model_dump() if hasattr(record, "model_dump") else dict(record))
        row_id = r_dict.get("rowId")
        is_blank = r_dict.get("isBlank", False)
        val_status = r_dict.get("validation_status")
        if val_status == "invalid":
            continue
        if (row_id is None or row_id not in error_row_ids) and not is_blank:
            valid_records.append(r_dict)

    if not valid_records and records:
        valid_records = [
            (r if isinstance(r, dict) else r.model_dump())
            for r in records
            if (r if isinstance(r, dict) else r.model_dump()).get("validation_status") != "invalid"
        ]

    res = await EmployeeIngestionService.process_ingestion(valid_records, db, imported_by)

    if upload_id:
        try:
            history_record = await upload_history_repository.get(db, uuid.UUID(str(upload_id)))
            if history_record:
                history_record.status = "IMPORTED"
                db.add(history_record)
                await db.commit()
        except Exception:
            pass

    return res
