import os
import uuid
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import openpyxl

from app.api.vendor.dependencies import get_db
from app.utils.response import success_response, error_response
from app.schemas.vendor import VendorUpdate, VendorResponse, VendorPreview
from app.services import vendor_service
from app.services.vendor_ingestion_service import VendorIngestionService
from app.services.vendor_upload_service import process_vendor_excel_upload, process_vendor_manual_entry
from app.services.vendor_validation_service import VendorValidationService

# Document Extraction Framework Imports (Removed obsolete imports)
from app.db.models.agreement import AgreementDocument, AgreementExtractionResult
from app.db.models.upload import UploadHistory

router = APIRouter()

# ---------------------------------------------------------------------------
# 1. Existing Vendor Ingestion APIs (Excel Upload, Manual, Preview, Import)
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_vendors(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return error_response(message="Invalid file format. Only Excel (.xlsx, .xls) files are allowed.")
        
    try:
        result = await process_vendor_excel_upload(file, db, uploaded_by="system_upload")
        return success_response(message="Vendor Excel upload preview generated successfully", data=result)
    except Exception as e:
        logger.exception("Error processing vendor upload")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/manual")
async def manual_vendors(data: list[dict], db: AsyncSession = Depends(get_db)):
    try:
        result = await process_vendor_manual_entry(data, db, uploaded_by="system_manual")
        return success_response(message="Vendor manual entry preview generated successfully", data=result)
    except Exception as e:
        logger.exception("Error processing vendor manual entry")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/preview")
async def preview_vendors(data: list[dict], db: AsyncSession = Depends(get_db)):
    try:
        result = await process_vendor_manual_entry(data, db, uploaded_by="system_preview")
        return success_response(message="Preview generated successfully", data=result)
    except Exception as e:
        logger.exception("Error processing vendor preview")
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/import")
async def import_vendors(payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records and isinstance(payload, list):
            records = payload

        # Pre-import validation: verify 11 required fields
        invalid_records = []
        for idx, rec in enumerate(records):
            val_res = VendorValidationService.validate_preview_row(rec)
            if not val_res.ready_to_import:
                invalid_records.append({
                    "row_id": rec.get("rowId") or f"ROW_{idx+1}",
                    "vendor_id": rec.get("vendor_id"),
                    "missing_required_fields": val_res.missing_required_fields
                })

        if invalid_records:
            return error_response(
                message=f"Import blocked. Missing required fields in preview records.",
                errors=invalid_records,
                status_code=http_status.HTTP_400_BAD_REQUEST
            )

        # Execute final import into vendor_master
        result = await VendorIngestionService.process_records(records, db, imported_by="system_import")
        return success_response(message="Vendor import completed successfully", data=result)
    except Exception as e:
        logger.exception("Critical error during vendor import")
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
    Upload an agreement PDF/DOCX document for a specific vendor preview row.
    Triggers extraction in the background.
    """
    try:
        doc = await DocumentService.save_uploaded_agreement(
            file=file,
            preview_row_id=row_id,
            entity_type="vendor",
            upload_id=upload_id,
            db=db
        )
        
        # Trigger background extraction
        background_tasks.add_task(
            background_extraction_task,
            document_id=str(doc.id),
            preview_row_id=row_id,
            upload_id=upload_id,
            entity_type="vendor"
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
            entity_type="vendor"
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

# ---------------------------------------------------------------------------
# 3. Existing Vendor Management CRUD APIs (List, Get, Update, Delete)
# ---------------------------------------------------------------------------

@router.get("", response_model=None)
async def list_vendors(
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    recurring: Optional[str] = None,
    currency: Optional[str] = None,
    contract_type: Optional[str] = None,
    payment_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await vendor_service.get_vendors(
            db=db, skip=skip, limit=limit, search=search,
            industry=industry, status=status, recurring=recurring,
            currency=currency, contract_type=contract_type, payment_type=payment_type
        )
        return success_response(message="Vendors fetched successfully", data=result)
    except Exception as e:
        logger.exception("Error fetching vendors")
        return error_response(message=str(e), status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    try:
        vendor = await vendor_service.get_vendor_by_key(db, vendor_id, category)
        if not vendor:
            return error_response(message="Vendor not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        return success_response(
            message="Vendor fetched successfully",
            data=VendorResponse.model_validate(vendor).model_dump(mode="json")
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.put("/{vendor_id}")
async def update_vendor(vendor_id: str, vendor_in: VendorUpdate, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    try:
        vendor = await vendor_service.get_vendor_by_key(db, vendor_id, category or vendor_in.category)
        if not vendor:
            return error_response(message="Vendor not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        update_data = vendor_in.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            if hasattr(vendor, k):
                setattr(vendor, k, v)
        await db.commit()
        await db.refresh(vendor)
        return success_response(
            message="Vendor updated successfully",
            data=VendorResponse.model_validate(vendor).model_dump(mode="json")
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    try:
        success = await vendor_service.delete_vendor(db, vendor_id, category)
        if not success:
            return error_response(message="Vendor not found", status_code=http_status.HTTP_404_NOT_FOUND)
        return success_response(message="Vendor deleted successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)
