from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, UUID4

class ValidationLogBase(BaseModel):
    row_number: Optional[int] = None
    field_name: Optional[str] = None
    invalid_value: Optional[str] = None
    error_message: Optional[str] = None
    severity: Optional[str] = None

class ValidationLogResponse(ValidationLogBase):
    id: UUID4
    upload_history_id: UUID4
    model_config = ConfigDict(from_attributes=True)

class ImportLogBase(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    action: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None

class ImportLogResponse(ImportLogBase):
    id: UUID4
    upload_history_id: UUID4
    model_config = ConfigDict(from_attributes=True)

class UploadHistoryBase(BaseModel):
    upload_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[str] = None
    total_records: Optional[int] = 0
    success_records: Optional[int] = 0
    failed_records: Optional[int] = 0
    processing_time: Optional[int] = None
    status: Optional[str] = None
    preview_data: Optional[Any] = None

class UploadHistoryCreate(UploadHistoryBase):
    pass

class UploadHistoryUpdate(UploadHistoryBase):
    pass

class UploadHistoryResponse(UploadHistoryBase):
    id: UUID4
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UploadHistoryListResponse(BaseModel):
    items: List[UploadHistoryResponse]
    total: int
    page: int
    size: int
