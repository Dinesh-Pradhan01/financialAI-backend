from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.db.models.employee import EmployeeMaster
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

class RepositoryEmployee(BaseRepository[EmployeeMaster, EmployeeCreate, EmployeeUpdate]):
    async def get_by_emp_id(self, db: AsyncSession, emp_id: str) -> Optional[EmployeeMaster]:
        query = select(EmployeeMaster).where(
            EmployeeMaster.employee_id == emp_id,
            EmployeeMaster.is_deleted == False
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def soft_delete_by_emp_id(self, db: AsyncSession, emp_id: str) -> Optional[EmployeeMaster]:
        obj = await self.get_by_emp_id(db, emp_id)
        if obj:
            obj.is_deleted = True
            db.add(obj)
            await db.commit()
        return obj

employee_repository = RepositoryEmployee(EmployeeMaster)

