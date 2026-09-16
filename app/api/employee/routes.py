from fastapi import APIRouter, Depends, UploadFile, File, Query, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional

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
    Parses, validates, and returns preview data.
    Does NOT mutate permanent employee database.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        return error_response("Invalid file type. Only Excel files are allowed.")
        
    try:
        preview_res = await process_employee_excel_upload(file, db)
        return success_response("Employee file processed successfully. Preview ready for review.", data=preview_res)
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
    Validates and returns preview data.
    Does NOT mutate permanent employee database.
    """
    try:
        preview_res = await process_employee_manual_entry(data, db)
        return success_response("Employee manual entry processed successfully. Preview ready for review.", data=preview_res)
    except Exception as e:
        return error_response(f"An unexpected error occurred: {str(e)}", status_code=500)

@router.post("/preview")
async def preview_employees(
    data: List[Dict[str, Any]] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate employee preview data for HR review and editing.
    Does NOT mutate permanent employee database.
    """
    try:
        preview_res = await process_employee_manual_entry(data, db)
        return success_response("Employee preview generated successfully.", data=preview_res)
    except Exception as e:
        return error_response(f"An unexpected error occurred: {str(e)}", status_code=500)

@router.post("/import")
async def import_validated_employees(
    preview_data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Bulk import validated employees.
    ONLY endpoint in the workflow that permanently writes/updates employee records.
    """
    try:
        result = await import_employees(preview_data, db)
        return success_response("Employees imported successfully", data=result)
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

@router.get("/{employee_id}")
async def get_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Return complete employee details by employee_id string PK.
    """
    emp = await get_employee_by_id(db, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return success_response("Employee fetched successfully", data=emp.model_dump())

@router.put("/{employee_id}")
async def update_employee_details(
    employee_id: str,
    emp_in: EmployeeUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update employee details by employee_id string PK.
    """
    try:
        updated_emp = await update_employee(db, employee_id, emp_in)
        if not updated_emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        return success_response("Employee updated successfully", data=updated_emp.model_dump())
    except ValueError as ve:
        return error_response(str(ve), status_code=400)

@router.delete("/{employee_id}")
async def delete_employee_record(
    employee_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete employee by employee_id string PK.
    """
    success = await delete_employee(db, employee_id)
    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")
    return success_response("Employee deleted successfully")

