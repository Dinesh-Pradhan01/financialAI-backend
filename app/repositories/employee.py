from app.repositories.base import BaseRepository
from app.db.models.employee import EmployeeMaster
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

class RepositoryEmployee(BaseRepository[EmployeeMaster, EmployeeCreate, EmployeeUpdate]):
    pass

employee_repository = RepositoryEmployee(EmployeeMaster)
