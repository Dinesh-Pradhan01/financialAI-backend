from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.utils.response import success_response, error_response
from app.services.dashboard_service import (
    get_employee_dashboard_metrics,
    get_vendor_dashboard_metrics,
    get_recent_activity,
    get_upload_preview
)

router = APIRouter()
cfo_dashboard_router = APIRouter()

@router.get("/employee")
async def get_employee_dashboard(db: AsyncSession = Depends(get_db)):
    try:
        metrics = await get_employee_dashboard_metrics(db)
        return success_response("Employee metrics fetched successfully", data=metrics)
    except Exception as e:
        return error_response(f"Failed to fetch employee metrics: {str(e)}", status_code=500)

@cfo_dashboard_router.get("/vendor")
async def get_vendor_dashboard(db: AsyncSession = Depends(get_db)):
    try:
        metrics = await get_vendor_dashboard_metrics(db)
        return success_response("Vendor metrics fetched successfully", data=metrics)
    except Exception as e:
        return error_response(f"Failed to fetch vendor metrics: {str(e)}", status_code=500)

@router.get("/history")
async def get_history(db: AsyncSession = Depends(get_db)):
    try:
        activities = await get_recent_activity(db, scope="hr")
        return success_response("History fetched successfully", data=activities)
    except Exception as e:
        return error_response(f"Failed to fetch history: {str(e)}", status_code=500)

@router.get("/history/{upload_id}/preview")
async def get_preview(upload_id: str, db: AsyncSession = Depends(get_db)):
    try:
        preview_data = await get_upload_preview(db, upload_id, scope="hr")
        if preview_data is None:
            return error_response(f"Upload preview not found for ID '{upload_id}'", status_code=404)
        return success_response("Preview fetched successfully", data=preview_data)
    except Exception as e:
        return error_response(f"Failed to fetch preview: {str(e)}", status_code=500)

@cfo_dashboard_router.get("/history")
async def get_cfo_history(db: AsyncSession = Depends(get_db)):
    try:
        activities = await get_recent_activity(db, scope="cfo")
        return success_response("History fetched successfully", data=activities)
    except Exception as e:
        return error_response(f"Failed to fetch history: {str(e)}", status_code=500)

@cfo_dashboard_router.get("/history/{upload_id}/preview")
async def get_cfo_preview(upload_id: str, db: AsyncSession = Depends(get_db)):
    try:
        preview_data = await get_upload_preview(db, upload_id, scope="cfo")
        if preview_data is None:
            return error_response(f"Upload preview not found for ID '{upload_id}'", status_code=404)
        return success_response("Preview fetched successfully", data=preview_data)
    except Exception as e:
        return error_response(f"Failed to fetch preview: {str(e)}", status_code=500)
