import os
import uuid
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, status as http_status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import openpyxl

from app.api.vendor.dependencies import get_db
from app.auth.dependencies import get_current_session_user
from app.utils.response import success_response, error_response
from app.schemas.client import ClientUpdate, ClientResponse, ClientPreview
from app.services import client_service
from app.services.client_ingestion_service import ClientIngestionService
from app.services.client_upload_service import process_client_excel_upload, process_client_manual_entry
from app.services.client_validation_service import ClientValidationService

# Document Extraction Framework Imports
from app.db.models.agreement import AgreementDocument, AgreementExtractionResult
from app.db.models.upload import UploadHistory

router = APIRouter()

# ---------------------------------------------------------------------------
# 1. Existing Client Ingestion APIs (Excel Upload, Manual, Preview, Import)
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_clients(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return error_response("Invalid file format. Only Excel (.xlsx, .xls) files are allowed.")
    try:
        from app.upload_engine.services.upload_engine import UploadEngine
        engine = UploadEngine("client")
        preview_data = await engine.process_file(file, db, uploaded_by=str(current_user.id), business_id=current_user.business_id)
        return success_response("Client Excel upload preview generated successfully", data=preview_data)
    except Exception as exc:
        return error_response(str(exc), status_code=400)
    
@router.post("/manual")
async def manual_clients(data: list[dict], db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    if data is None:
        return error_response("Client payload is required.")
    if isinstance(data, list):
        records = data
    else:
        records = [data]
    try:
        from app.upload_engine.services.upload_engine import UploadEngine
        engine = UploadEngine("client")
        preview_data = await engine.process_manual(records, db, uploaded_by=str(current_user.id), business_id=current_user.business_id)
        return success_response("Client manual entry preview generated successfully", data=preview_data)
    except Exception as exc:
        return error_response(str(exc), status_code=400)

@router.post("/preview")
async def preview_clients(data: list[dict], db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    if data is None:
        return error_response("Preview payload is required.")
    try:
        from app.upload_engine.services.upload_engine import UploadEngine
        engine = UploadEngine("client")
        preview_data = await engine.process_manual(data, db, uploaded_by=str(current_user.id), business_id=current_user.business_id)
        return success_response("Client preview generated successfully", data=preview_data)
    except Exception as exc:
        return error_response(str(exc), status_code=400)

@router.post("/import")
async def import_clients(payload: dict, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    try:
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records and isinstance(payload, list):
            records = payload

        # Pre-import validation: verify required fields
        invalid_records = []
        for idx, rec in enumerate(records):
            val_res = ClientValidationService.validate_preview_row(rec)
            if not val_res.ready_to_import:
                invalid_records.append({
                    "row_id": rec.get("rowId") or f"ROW_{idx+1}",
                    "client_id": rec.get("client_id"),
                    "missing_required_fields": val_res.missing_required_fields
                })

        if invalid_records:
            return error_response(
                message=f"Import blocked. Missing required fields in preview records.",
                errors=invalid_records,
                status_code=http_status.HTTP_400_BAD_REQUEST
            )

        # Execute final import into client_master
        result = await ClientIngestionService.process_records(records, db, imported_by=str(current_user.id), business_id=str(current_user.business_id))
        return success_response(message="Client import completed successfully", data=result)
    except Exception as e:
        logger.exception("Critical error during client import")
        return error_response(message=f"Critical Import Error: {str(e)}", status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# 2. Agreement Document Extraction APIs
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
        logger.error("No session factory available for background task.")
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
            logger.exception(f"Background extraction failed for doc {document_id}: {e}")


@router.post("/preview/{upload_id}/row/{row_id}/agreement")
async def upload_agreement_document(
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

        # Trigger background extraction
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
        return error_response(message=de.message, status_code=http_status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(f"Error uploading agreement for row '{row_id}'")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/preview/{upload_id}/row/{row_id}/agreement/extract")
async def extract_agreement_data(
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
                status_code=http_status.HTTP_404_NOT_FOUND
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
        return error_response(message=de.message, status_code=http_status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Critical error during agreement extraction")
        return error_response(
            message=f"Critical Extraction Error: {str(e)}",
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/preview/{upload_id}/row/{row_id}/agreement/extraction")
async def get_agreement_extraction_status(
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
                status_code=http_status.HTTP_404_NOT_FOUND
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
        logger.exception("Error fetching agreement extraction status")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.get("/preview/{upload_id}/row/{row_id}/agreement/file")
async def get_agreement_file(
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
                status_code=http_status.HTTP_404_NOT_FOUND
            )
        return FileResponse(
            path=doc.file_path,
            filename=doc.file_name,
            media_type=doc.mime_type or "application/pdf"
        )
    except Exception as e:
        logger.exception("Error streaming agreement file")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

# ---------------------------------------------------------------------------
# 3. Existing Client Management CRUD APIs (List, Get, Update, Delete)
# ---------------------------------------------------------------------------

@router.get("", response_model=None)
async def list_clients(
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    recurring: Optional[str] = None,
    currency: Optional[str] = None,
    contract_type: Optional[str] = None,
    payment_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_session_user)
):
    try:
        result = await client_service.get_clients(
            db=db, business_id=str(current_user.business_id), skip=skip, limit=limit, search=search,
            industry=industry, status=status, recurring=recurring,
            currency=currency, contract_type=contract_type, payment_type=payment_type
        )
        return success_response(message="Clients fetched successfully", data=result)
    except AttributeError:
        # Fallback if get_clients doesn't exist on client_service and uses list_clients instead
        try:
            items = await client_service.ClientService.list_clients(db, business_id=str(current_user.business_id), skip=skip, limit=limit)
            return success_response("Clients fetched successfully", data={"items": [i.__dict__ for i in items], "total": len(items), "page": (skip//limit)+1, "size": limit})
        except Exception as e:
            logger.exception("Error fetching clients")
            return error_response(message=str(e), status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.exception("Error fetching clients")
        return error_response(message=str(e), status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

@router.get("/{client_id}")
async def get_client(client_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    try:
        # Use ClientService.get_client 
        client = await client_service.ClientService.get_client(db, str(current_user.business_id), client_id, category)
        if not client:
            return error_response(message="Client not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        # We don't want to enforce Pydantic dumps if it causes errors, we just return __dict__
        data = client.__dict__.copy()
        if "_sa_instance_state" in data:
            del data["_sa_instance_state"]
        return success_response(
            message="Client fetched successfully",
            data=data
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.put("/{client_id}")
async def update_client(client_id: str, client_in: ClientUpdate, category: Optional[str] = None, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    try:
        client = await client_service.ClientService.get_by_business_key(db, client_id, category or client_in.category)
        if not client:
            return error_response(message="Client not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        update_data = client_in.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            if hasattr(client, k):
                setattr(client, k, v)
        await db.commit()
        await db.refresh(client)
        data = client.__dict__.copy()
        if "_sa_instance_state" in data:
            del data["_sa_instance_state"]
        return success_response(
            message="Client updated successfully",
            data=data
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.delete("/{client_id}")
async def delete_client(client_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_session_user)):
    try:
        success = await client_service.ClientService.delete_client(db, str(current_user.business_id), client_id, category)
        if not success:
            return error_response(message="Client not found", status_code=http_status.HTTP_404_NOT_FOUND)
        return success_response(message="Client deleted successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

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
            import json
            import os
            obj = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_id))
            history = obj.scalars().first()
            if history:
                data = history.preview_data or {"records": [], "summary": {}}
                schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "upload_engine", "config", "schemas", "client_schema.json")
                try:
                    with open(schema_path, "r") as f:
                        data["schema_def"] = json.load(f)
                except Exception:
                    data["schema_def"] = {"fields": []}
                return success_response("Client upload preview fetched successfully", data=data)
    return error_response("Upload not found", status_code=404)

