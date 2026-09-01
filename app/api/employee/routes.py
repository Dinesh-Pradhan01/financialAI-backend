from fastapi import APIRouter, Depends, UploadFile, File, Query, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
import uuid

from app.api.employee.dependencies import get_db
from app.utils.response import success_response, error_response
from app.schemas.employee import EmployeePreviewResponse, EmployeeUpdate
from app.services.employee_upload_service import process_employee_excel_upload, process_employee_manual_entry
from app.services.employee_import_service import import_employees
from app.services.employee_service import get_employees, get_employee_by_id, update_employee, delete_employee

router = APIRouter()

@router.post("/upload")
async def upload_employee_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload Employee Excel.
    Accepts multipart/form-data. Stores file locally, parses, normalizes, validates, and returns preview.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        return error_response("Invalid file type. Only Excel files are allowed.")
        
    try:
        preview_data = await process_employee_excel_upload(file, db)
        return success_response("Preview generated successfully", data=preview_data)
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f"An unexpected error occurred: {str(e)}", status_code=500)

@router.post("/manual")
async def manual_employee_entry(
    data: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Accept manual entry JSON.
    Normalizes, validates, and returns preview.
    """
    try:
        preview_data = await process_employee_manual_entry(data, db)
        return success_response("Preview generated successfully", data=preview_data)
    except Exception as e:
        return error_response(f"An unexpected error occurred: {str(e)}", status_code=500)

@router.post("/preview")
async def preview_employees(
    data: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns normalized preview. Identical functionality to manual entry.
    """
    try:
        preview_data = await process_employee_manual_entry(data, db)
        return success_response("Preview generated successfully", data=preview_data)
    except Exception as e:
        return error_response(f"An unexpected error occurred: {str(e)}", status_code=500)

@router.post("/import")
async def import_validated_employees(
    preview_data: EmployeePreviewResponse = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Bulk insert all validated employees.
    Uses transaction. Rolls back on critical error. Stores import logs.
    """
    try:
        result = await import_employees(preview_data, db)
        if result["errors"]:
            return error_response("Import completed with errors", errors=result["errors"], status_code=207)
        return success_response("Import completed successfully", data=result)
    except Exception as e:
        return error_response(f"Failed to import employees: {str(e)}", status_code=500)

@router.get("")
async def list_employees(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    employment_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get employees with pagination, search, and filters.
    """
    skip = (page - 1) * size
    result = await get_employees(db, skip=skip, limit=size, search=search, department=department, status=status, employment_type=employment_type)
    return success_response("Employees fetched successfully", data=result.model_dump())

@router.get("/{id}")
async def get_employee(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Return complete employee details.
    """
    emp = await get_employee_by_id(db, id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return success_response("Employee fetched successfully", data=emp.model_dump())

@router.put("/{id}")
async def update_employee_details(
    id: uuid.UUID,
    emp_in: EmployeeUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update employee details.
    """
    updated_emp = await update_employee(db, id, emp_in)
    if not updated_emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return success_response("Employee updated successfully", data=updated_emp.model_dump())

@router.delete("/{id}")
async def delete_employee_record(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete employee.
    """
    success = await delete_employee(db, id)
    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")
    return success_response("Employee deleted successfully")
