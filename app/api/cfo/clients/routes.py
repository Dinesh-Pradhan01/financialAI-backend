from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.vendor.dependencies import get_db
from app.db.models.client import ClientMaster
from app.services.client_compare_service import ClientComparisonService
from app.services.client_service import ClientService
from app.services.client_validation_service import ClientValidationService
from app.utils.response import error_response, success_response

router = APIRouter()

REQUIRED_CLIENT_COLUMNS = {
    "client_id": "client_id",
    "client_name": "client_name",
    "legal_name": "legal_name",
    "category": "category",
    "industry": "industry",
    "contract_id": "contract_id",
    "contract_type": "contract_type",
    "contract_start_date": "contract_start_date",
    "contract_end_date": "contract_end_date",
    "contract_value": "contract_value",
    "currency": "currency",
    "revenue": "revenue",
    "payment_type": "payment_type",
    "frequency": "frequency",
    "recurring": "recurring",
    "bank_name": "bank_name",
    "account_holder_name": "account_holder_name",
    "account_number": "account_number",
    "ifsc_code": "ifsc_code",
    "status": "status",
}


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    # Insert space before capital letters to handle camelCase (e.g. contractValue -> contract Value)
    s = re.sub(r'(?<!^)(?=[A-Z])', ' ', s)
    return s.lower().replace("_", " ").replace("-", " ")


def _normalize_row(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, val in record.items():
        canonical = None
        cleaned = _normalize_key(key)
        for canonical_key, variations in REQUIRED_CLIENT_COLUMNS.items():
            if cleaned == canonical_key.replace("_", " ") or cleaned == variations.replace("_", " "):
                canonical = canonical_key
                break
        if canonical is None:
            continue
        normalized[canonical] = val
    return normalized


async def _preview_record(record: Dict[str, Any], db: AsyncSession, is_upload: bool = False) -> Dict[str, Any]:
    normalized = _normalize_row(record)
    validation = ClientValidationService.validate_record(normalized, is_upload=is_upload)
    business_key = ClientComparisonService.business_key(normalized)
    existing = await ClientService.get_by_business_key(db, business_key[0], business_key[1]) if business_key[0] and business_key[1] else None
    if not validation["valid"]:
        return {
            **normalized,
            "validation_status": "invalid",
            "validation_errors": validation["errors"],
            "preview_status": "rejected",
            "action": "REJECT",
        }
    if existing is None:
        return {**normalized, "validation_status": "valid", "validation_errors": [], "preview_status": "new", "action": "INSERT"}
    comparison = ClientComparisonService.compare_record(existing.__dict__, normalized)
    return {
        **normalized,
        "validation_status": "valid",
        "validation_errors": [],
        "preview_status": "existing",
        "action": comparison["action"],
        "changed_fields": comparison.get("changed_fields", []),
        "existing_record": existing.__dict__,
    }


def _get_client_schema_def() -> dict:
    from app.services.client_validation_service import REQUIRED_FIELDS
    fields = []
    for k in REQUIRED_CLIENT_COLUMNS.keys():
        fields.append({
            "name": k,
            "required": k in REQUIRED_FIELDS,
            "type": "number" if k in {"contract_value", "revenue"} else "string"
        })
    return {"fields": fields}


@router.post("/upload")
async def upload_clients(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return error_response("Invalid file format. Only Excel (.xlsx, .xls) files are allowed.")
    try:
        import openpyxl

        import io
        contents = await file.read()
        workbook = openpyxl.load_workbook(filename=io.BytesIO(contents), read_only=True)
        sheet = workbook.active
        rows = []
        headers = []
        import math
        for row in sheet.iter_rows(values_only=True):
            if not headers:
                headers = [str(cell).strip() if cell is not None else "" for cell in row]
                continue
            if all((cell is None or str(cell).strip() == "") for cell in row):
                continue
            clean_row = [None if isinstance(cell, float) and math.isnan(cell) else cell for cell in row]
            rows.append(dict(zip(headers, clean_row)))

        preview_records = []
        for idx, record in enumerate(rows, start=2):
            normalized = _normalize_row(record)
            validated = ClientValidationService.validate_record(normalized, is_upload=True)
            preview_records.append({
                **normalized,
                "row": idx,
                "source_row": idx,
                "validation_status": "valid" if validated["valid"] else "invalid",
                "validation_errors": validated["errors"],
                "action": "REJECT" if not validated["valid"] else "INSERT",
                "preview_status": "new",
                "existing_status": "new",
                "duplicate_status": "new",
                "changed_fields": [],
                "is_blank": False,
            })

        import uuid
        import time
        from app.db.models.upload import UploadHistory
        
        upload_uuid = uuid.uuid4()
        upload_id = str(upload_uuid)
        
        preview_data = {
            "upload_id": upload_id,
            "records": preview_records,
            "schema_def": _get_client_schema_def(),
            "summary": {"validRecords": sum(1 for r in preview_records if r["validation_status"] == "valid"), "errors": sum(1 for r in preview_records if r["validation_status"] != "valid")},
        }
        
        history_record = UploadHistory(
            id=upload_uuid,
            upload_type="CLIENT_UPLOAD",
            file_name=file.filename,
            file_size=file.size,
            uploaded_by="system",
            total_records=len(preview_records),
            success_records=preview_data["summary"]["validRecords"],
            failed_records=preview_data["summary"]["errors"],
            processing_time=0,
            status="PREVIEW",
            preview_data=preview_data
        )
        db.add(history_record)
        await db.commit()

        return success_response("Client Excel upload preview generated successfully", data=preview_data)
    except Exception as exc:
        return error_response(str(exc), status_code=400)


@router.post("/manual")
async def manual_client_entry(data: Dict[str, Any] = None, db: AsyncSession = Depends(get_db)):
    if data is None:
        return error_response("Client payload is required.")
    if isinstance(data, list):
        records = data
    else:
        records = [data]
    preview = []
    for row_idx, item in enumerate(records, start=1):
        preview.append(await _preview_record(item, db, is_upload=True))
        
    import uuid
    from app.db.models.upload import UploadHistory
    
    upload_uuid = uuid.uuid4()
    upload_id = str(upload_uuid)
    
    preview_data = {
        "upload_id": upload_id,
        "records": preview, 
        "schema_def": _get_client_schema_def(),
        "summary": {
            "validRecords": sum(1 for r in preview if r.get("action") != "REJECT"), 
            "errors": sum(1 for r in preview if r.get("action") == "REJECT")
        }
    }
    
    history_record = UploadHistory(
        id=upload_uuid,
        upload_type="CLIENT_MANUAL",
        file_name="manual_entry.json",
        file_size=0,
        uploaded_by="system",
        total_records=len(preview),
        success_records=preview_data["summary"]["validRecords"],
        failed_records=preview_data["summary"]["errors"],
        processing_time=0,
        status="PREVIEW",
        preview_data=preview_data
    )
    db.add(history_record)
    await db.commit()
    
    return success_response("Client manual entry preview generated successfully", data=preview_data)


@router.post("/preview")
async def preview_clients(data: List[Dict[str, Any]] = None, db: AsyncSession = Depends(get_db)):
    if data is None:
        return error_response("Preview payload is required.")
    preview = []
    for row_idx, item in enumerate(data, start=1):
        preview.append(await _preview_record(item, db, is_upload=True))
        
    import uuid
    from app.db.models.upload import UploadHistory
    
    upload_uuid = uuid.uuid4()
    upload_id = str(upload_uuid)
    
    preview_data = {
        "upload_id": upload_id,
        "records": preview, 
        "schema_def": _get_client_schema_def(),
        "summary": {
            "validRecords": sum(1 for r in preview if r.get("action") != "REJECT"), 
            "errors": sum(1 for r in preview if r.get("action") == "REJECT")
        }
    }
    
    history_record = UploadHistory(
        id=upload_uuid,
        upload_type="CLIENT_PREVIEW",
        file_name="preview.json",
        file_size=0,
        uploaded_by="system",
        total_records=len(preview),
        success_records=preview_data["summary"]["validRecords"],
        failed_records=preview_data["summary"]["errors"],
        processing_time=0,
        status="PREVIEW",
        preview_data=preview_data
    )
    db.add(history_record)
    await db.commit()
    
    return success_response("Client preview generated successfully", data=preview_data)


@router.post("/import")
async def import_clients(payload: Dict[str, Any] = None, db: AsyncSession = Depends(get_db)):
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not records:
        return error_response("No records to import.")
    if isinstance(records, dict):
        records = [records]
    import_result = await ClientService.import_records(db, records)
    return success_response("Clients import completed successfully", data=import_result)


@router.get("")
async def list_clients(db: AsyncSession = Depends(get_db), page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=1000)):
    items = await ClientService.list_clients(db, skip=(page - 1) * size, limit=size)
    return success_response("Clients fetched successfully", data={"items": [i.__dict__ for i in items], "total": len(items), "page": page, "size": size})


@router.get("/{client_id}")
async def get_client(client_id: str, category: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    client = await ClientService.get_client(db, client_id, category)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return success_response("Client fetched successfully", data=client.__dict__)


@router.delete("/{client_id}")
async def delete_client(client_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    try:
        success = await ClientService.delete_client(db, client_id, category)
        if not success:
            return error_response(message="Client not found", status_code=404)
        return success_response(message="Client deleted successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


# ---------------------------------------------------------------------------
# 3. Agreement Document Extraction APIs
# ---------------------------------------------------------------------------

from app.services.agreement import (
    DocumentService,
    ExtractionService,
    AgreementExtractionBaseException
)
from fastapi import UploadFile, File, Form, Depends, Query, BackgroundTasks
from app.database.connection import db_manager

async def background_extraction_task(document_id: str, preview_row_id: str, upload_id: str, entity_type: str):
    """Runs extraction in the background using an isolated DB session."""
    if not db_manager.session_factory:
        return
    async with db_manager.session_factory() as db:
        try:
            await ExtractionService.process_extraction(
                document_id=document_id,
                preview_row_id=preview_row_id,
                upload_id=upload_id,
                entity_type=entity_type,
                db=db
            )
        except Exception as e:
            pass

@router.post("/preview/{upload_id}/row/{row_id}/agreement")
async def upload_agreement_document_client(
    upload_id: str,
    row_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload an agreement PDF/DOCX document for a specific client preview row.
    Triggers extraction in the background.
    """
    try:
        doc = await DocumentService.save_uploaded_agreement(
            file=file,
            preview_row_id=row_id,
            entity_type="client",
            upload_id=upload_id,
            db=db
        )

        background_tasks.add_task(
            background_extraction_task,
            document_id=str(doc.id),
            preview_row_id=row_id,
            upload_id=upload_id,
            entity_type="client"
        )

        return success_response(
            message="Agreement document uploaded and extraction started in background.",
            data={
                "document_id": str(doc.id),
                "preview_row_id": doc.preview_row_id,
                "upload_id": doc.upload_id,
                "file_name": doc.file_name,
                "status": "PROCESSING"
            }
        )
    except AgreementExtractionBaseException as de:
        return error_response(message=de.message, status_code=400)
    except Exception as e:
        return error_response(message=str(e), status_code=400)

@router.post("/preview/{upload_id}/row/{row_id}/agreement/extract")
async def extract_agreement_data_client(
    upload_id: str,
    row_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Run document text extraction, OCR fallback, and Gemini LLM structured parsing in the background.
    """
    try:
        doc = await DocumentService.get_active_document(row_id, db)
        if not doc:
            return error_response(
                message=f"No uploaded agreement found for preview row '{row_id}'. Please upload an agreement first.",
                status_code=404
            )

        doc.status = "PROCESSING"
        await db.commit()

        background_tasks.add_task(
            background_extraction_task,
            document_id=str(doc.id),
            preview_row_id=row_id,
            upload_id=upload_id,
            entity_type="client"
        )

        return success_response(
            message="Agreement extraction triggered in the background successfully.",
            data={
                "document_id": str(doc.id),
                "preview_row_id": doc.preview_row_id,
                "upload_id": doc.upload_id,
                "file_name": doc.file_name,
                "status": "PROCESSING"
            }
        )
    except AgreementExtractionBaseException as de:
        return error_response(message=de.message, status_code=400)
    except Exception as e:
        return error_response(
            message=f"Critical Extraction Error: {str(e)}",
            status_code=500
        )

@router.get("/preview/{upload_id}/row/{row_id}/agreement/extraction")
async def get_agreement_extraction_status_client(
    upload_id: str,
    row_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the latest extraction result and confidence scores for a specific row's agreement.
    """
    try:
        doc = await DocumentService.get_active_document(row_id, db)
        if not doc:
            return error_response(
                message=f"No uploaded agreement found for preview row '{row_id}'.",
                status_code=404
            )
        
        extraction = await DocumentService.get_latest_extraction(doc.id, db)
        if not extraction:
            return success_response(
                message="Document uploaded but not extracted yet.",
                data={
                    "status": doc.status,
                    "document_id": str(doc.id),
                    "file_name": doc.file_name
                }
            )

        return success_response(
            message="Extraction result retrieved successfully.",
            data={
                "status": doc.status,
                "document_id": str(doc.id),
                "file_name": doc.file_name,
                "extracted_data": {
                    "contract_start_date": str(extraction.contract_start_date) if extraction.contract_start_date else None,
                    "contract_end_date": str(extraction.contract_end_date) if extraction.contract_end_date else None,
                    "contract_value": float(extraction.contract_value) if extraction.contract_value is not None else None,
                    "currency": extraction.currency,
                    "contract_type": extraction.contract_type
                },
                "field_confidence": extraction.field_confidence
            }
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)

@router.get("/preview/{upload_id}/row/{row_id}/agreement/file")
async def get_agreement_file_client(
    upload_id: str,
    row_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream the uploaded agreement file for viewing or downloading.
    """
    try:
        doc = await DocumentService.get_active_document(row_id, db)
        if not doc or not doc.file_path or not os.path.exists(doc.file_path):
            return error_response(
                message=f"No agreement file found for preview row '{row_id}'.",
                status_code=404
            )
        return FileResponse(
            path=doc.file_path,
            filename=doc.file_name,
            media_type=doc.mime_type or "application/pdf"
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@router.put("/{client_id}")
async def update_client(client_id: str, payload: Dict[str, Any] = None, category: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    if payload is None:
        return error_response("Client payload is required.")
    target_category = payload.get("category") or category
    if not target_category:
        return error_response("Category is required to identify the client because the business key is client_id + category.")
    existing = await ClientService.get_by_business_key(db, client_id, target_category)
    if existing is None:
        raise HTTPException(status_code=404, detail="Client not found")
    update_payload = payload.copy()
    validation = ClientValidationService.validate_record({**existing.__dict__, **update_payload})
    if not validation["valid"]:
        return error_response("Client update validation failed", errors=validation["errors"], status_code=400)
    for field in [
        "client_name", "legal_name", "category", "industry", "contract_id", "contract_type", "contract_start_date",
        "contract_end_date", "contract_value", "currency", "revenue", "payment_type", "frequency", "recurring",
        "bank_name", "account_holder_name", "account_number", "ifsc_code", "status",
    ]:
        if field in update_payload:
            setattr(existing, field, update_payload[field])
    await db.commit()
    return success_response("Client updated successfully", data=existing.__dict__)


@router.get("/dashboard/history")
async def get_client_history(db: AsyncSession = Depends(get_db)):
    from app.services.dashboard_service import get_recent_activity
    try:
        activities = await get_recent_activity(db, scope="cfo")
        client_history = [item for item in activities if item.get("upload_type") == "Client"]
        return success_response("Client history fetched successfully", data=client_history)
    except Exception as e:
        return error_response(f"Failed to fetch client history: {str(e)}", status_code=500)


@router.get("/dashboard/history/{upload_id}/preview")
async def get_client_history_preview(upload_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.dashboard_service import get_recent_activity
    activities = await get_recent_activity(db, scope="cfo")
    for item in activities:
        if item.get("upload_id") == upload_id and item.get("upload_type") == "Client":
            from sqlalchemy import select
            from app.db.models.upload import UploadHistory
            obj = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_id))
            history = obj.scalars().first()
            if history:
                data = history.preview_data or {"records": [], "summary": {}}
                data["schema_def"] = _get_client_schema_def()
                return success_response("Client upload preview fetched successfully", data=data)
    return error_response("Upload not found", status_code=404)
