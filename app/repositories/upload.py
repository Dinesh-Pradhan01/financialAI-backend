from pydantic import BaseModel
from app.repositories.base import BaseRepository
from app.db.models.upload import UploadHistory, ValidationLogs, ImportLogs
from app.schemas.upload import UploadHistoryCreate, UploadHistoryUpdate

class RepositoryUploadHistory(BaseRepository[UploadHistory, UploadHistoryCreate, UploadHistoryUpdate]):
    pass

# We can use dummy Pydantic models for logs since they might not have update methods.
class DummyCreate(BaseModel): pass
class DummyUpdate(BaseModel): pass

class RepositoryValidationLogs(BaseRepository[ValidationLogs, DummyCreate, DummyUpdate]):
    pass

class RepositoryImportLogs(BaseRepository[ImportLogs, DummyCreate, DummyUpdate]):
    pass

upload_history_repository = RepositoryUploadHistory(UploadHistory)
validation_log_repository = RepositoryValidationLogs(ValidationLogs)
import_log_repository = RepositoryImportLogs(ImportLogs)
