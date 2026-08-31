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

async def get_employee_by_id(db: AsyncSession, id: uuid.UUID) -> Optional[EmployeeResponse]:
    obj = await employee_repository.get(db, id)
    if obj:
        return EmployeeResponse.model_validate(obj)
    return None

async def update_employee(db: AsyncSession, id: uuid.UUID, emp_in: EmployeeUpdate) -> Optional[EmployeeResponse]:
    db_obj = await employee_repository.get(db, id)
    if not db_obj:
        return None
    updated_obj = await employee_repository.update(db, db_obj=db_obj, obj_in=emp_in)
    return EmployeeResponse.model_validate(updated_obj)

async def delete_employee(db: AsyncSession, id: uuid.UUID) -> bool:
    obj = await employee_repository.soft_delete(db, id=id)
    return obj is not None
