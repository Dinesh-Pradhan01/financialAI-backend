import uuid
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date
from enum import Enum

class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_name: str
    hash_md5: str
    file_size_bytes: int
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AccountResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    bank_name: str
    account_holder_name: str
    account_number: str
    ifsc_code: Optional[str] = None
    branch: Optional[str] = None
    opening_balance: float
    closing_balance: float
    statement_period: Optional[str] = None
    statement_month: Optional[str] = None

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: date  # Represented as date object
    value_date: Optional[date] = None
    narration: str
    debit_amount: float
    credit_amount: float
    running_balance: float
    reference_number: Optional[str] = None
    utr_upi_ref: Optional[str] = None
    cheque_number: Optional[str] = None
    category: str
    type: str

    class Config:
        from_attributes = True

class ExtractedStatementResponse(BaseModel):
    document: DocumentResponse
    account: Optional[AccountResponse] = None
    transactions: List[TransactionResponse] = Field(default_factory=list)

class TransactionListResponse(BaseModel):
    total: int
    transactions: List[TransactionResponse]
