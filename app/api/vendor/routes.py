import uuid
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api.vendor.dependencies import get_db
from app.utils.response import success_response, error_response
from app.schemas.vendor import (
    VendorPreview, VendorCreate, VendorUpdate, VendorResponse
)
from app.services import vendor_upload_service, vendor_import_service, vendor_service

router = APIRouter()

@router.post("/upload")
async def upload_vendors(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        return error_response(message="Invalid file format. Only Excel (.xlsx) files are allowed.")
        
    try:
        preview = await vendor_upload_service.process_vendor_excel_upload(file, db)
        return success_response(message="Preview generated successfully", data=preview)
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/manual")
async def manual_vendors(data: list[dict], db: AsyncSession = Depends(get_db)):
    try:
        preview = await vendor_upload_service.process_vendor_manual_entry(data, db)
        return success_response(message="Preview generated successfully", data=preview)
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/preview")
async def preview_vendors(data: list[dict], db: AsyncSession = Depends(get_db)):
    try:
        preview = await vendor_upload_service.process_vendor_manual_entry(data, db)
        return success_response(message="Preview updated successfully", data=preview)
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.post("/import")
async def import_vendors(preview_data: VendorPreview, db: AsyncSession = Depends(get_db)):
    try:
        logger.info(f"Incoming Import Payload (Upload ID: {preview_data.upload_id})")
        result = await vendor_import_service.import_vendors(preview_data, db)
        if len(result.get("errors", [])) > 0:
            logger.error(f"Import completed with errors: {result['errors']}")
            return error_response(message="Import completed with errors", errors=result["errors"])
        return success_response(message="Import completed successfully", data=result)
    except Exception as e:
        logger.exception("Critical error during vendor import")
        return error_response(message=f"Critical Import Error: {str(e)}", status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

@router.get("", response_model=None)
async def list_vendors(
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    recurring: Optional[bool] = None,
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
        return error_response(message=str(e), status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

@router.get("/{id}")
async def get_vendor(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        vendor = await vendor_service.get_vendor_by_id(db, id)
        if not vendor:
            return error_response(message="Vendor not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        return success_response(
            message="Vendor fetched successfully",
            data=VendorResponse.model_validate(vendor).model_dump(mode="json")
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.put("/{id}")
async def update_vendor(id: uuid.UUID, vendor_in: VendorUpdate, db: AsyncSession = Depends(get_db)):
    try:
        vendor = await vendor_service.get_vendor_by_id(db, id)
        if not vendor:
            return error_response(message="Vendor not found", status_code=http_status.HTTP_404_NOT_FOUND)
        
        vendor = await vendor_service.update_vendor(db, db_obj=vendor, obj_in=vendor_in)
        return success_response(
            message="Vendor updated successfully",
            data=VendorResponse.model_validate(vendor).model_dump(mode="json")
        )
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)

@router.delete("/{id}")
async def delete_vendor(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        await vendor_service.delete_vendor(db, id)
        return success_response(message="Vendor deleted successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=http_status.HTTP_400_BAD_REQUEST)
