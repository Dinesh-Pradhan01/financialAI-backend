import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.repositories.employee import employee_repository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeListResponse, EmployeeResponse
from app.db.models.employee import EmployeeMaster

async def get_employees(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    search: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    employment_type: Optional[str] = None
) -> EmployeeListResponse:
    
    query = select(EmployeeMaster).where(EmployeeMaster.is_deleted == False)
    
    if search:
        query = query.where(
            or_(
                EmployeeMaster.employee_name.ilike(f"%{search}%"),
                EmployeeMaster.employee_id.ilike(f"%{search}%"),
                EmployeeMaster.email.ilike(f"%{search}%")
            )
        )
    if department:
        query = query.where(EmployeeMaster.department == department)
    if status:
        query = query.where(EmployeeMaster.status == status)
    if employment_type:
        query = query.where(EmployeeMaster.employment_type == employment_type)
        
    query = query.order_by(EmployeeMaster.created_at.desc())
    
    # count total
    total_query = select(EmployeeMaster).where(EmployeeMaster.is_deleted == False)
    if search or department or status or employment_type:
        # Just use the filtered query but without offset/limit
        count_result = await db.execute(select(query.subquery()))
        total = len(count_result.scalars().all()) # not the most efficient for big tables, but works. A true count query is better.
    else:
        total = await employee_repository.count(db)

    # Apply pagination
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return EmployeeListResponse(
        items=[EmployeeResponse.model_validate(item) for item in items],
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        size=limit
    )

async def get_employee_by_id(db: AsyncSession, emp_id: str) -> Optional[EmployeeResponse]:
    obj = await employee_repository.get_by_emp_id(db, emp_id)
    if obj:
        return EmployeeResponse.model_validate(obj)
    return None

async def update_employee(db: AsyncSession, emp_id: str, emp_in: EmployeeUpdate) -> Optional[EmployeeResponse]:
    db_obj = await employee_repository.get_by_emp_id(db, emp_id)
    if not db_obj:
        return None
    
    # Immutability Check: Do not allow changing employee_id
    if emp_in.employee_id and emp_in.employee_id != emp_id:
        raise ValueError("employee_id is immutable and cannot be changed.")
        
    update_data = emp_in.model_dump(exclude_unset=True)
    update_data.pop("employee_id", None)
    update_data["employee_id"] = emp_id

    # Construct complete dictionary for ingestion update
    full_dict = {
        "employee_id": emp_id,
        "employee_name": update_data.get("employee_name", db_obj.employee_name),
        "email": update_data.get("email", db_obj.email),
        "joining_date": update_data.get("joining_date", db_obj.joining_date),
        "department": update_data.get("department", db_obj.department),
        "designation": update_data.get("designation", db_obj.designation),
        "salary": update_data.get("salary", db_obj.salary),
        "account_number": update_data.get("account_number", db_obj.account_number),
        "ifsc_code": update_data.get("ifsc_code", db_obj.ifsc_code),
        "bank_name": update_data.get("bank_name", db_obj.bank_name),
        "employment_type": update_data.get("employment_type", db_obj.employment_type),
        "status": update_data.get("status", db_obj.status),
        "salary_frequency": update_data.get("salary_frequency", db_obj.salary_frequency),
        "account_holder_name": update_data.get("account_holder_name", db_obj.account_holder_name),
        "payment_mode": update_data.get("payment_mode", db_obj.payment_mode),
    }

    from app.services.employee_ingestion_service import EmployeeIngestionService
    ingest_res = await EmployeeIngestionService.process_ingestion([full_dict], db)
    
    updated_obj = await employee_repository.get_by_emp_id(db, emp_id)
    if updated_obj:
        return EmployeeResponse.model_validate(updated_obj)
    return None

async def delete_employee(db: AsyncSession, emp_id: str) -> bool:
    obj = await employee_repository.soft_delete_by_emp_id(db, emp_id=emp_id)
    return obj is not None
