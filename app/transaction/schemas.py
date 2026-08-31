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
    mime_type: Optional[str] = None
    document_type: str = "BANK_STATEMENT"
    status: DocumentStatus
    error_message: Optional[str] = None
    account_id: Optional[uuid.UUID] = None
    business_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AccountResponse(BaseModel):
    id: uuid.UUID
    business_id: Optional[uuid.UUID] = None
    bank_name: str
    account_holder_name: str
    account_number: str
    account_type: str = "savings"
    currency: str = "INR"
    ifsc_code: Optional[str] = None
    branch_name: Optional[str] = None
    status: str = "ACTIVE"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BankStatementDataResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    account_id: Optional[uuid.UUID] = None
    opening_balance: float
    closing_balance: float
    statement_period: Optional[str] = None
    statement_month: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TransactionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    account_id: uuid.UUID
    business_id: Optional[uuid.UUID] = None
    merchant_id: Optional[uuid.UUID] = None
    category_id: Optional[int] = None
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
    raw_category: Optional[str] = None
    classification: str = "expense"
    type: str

    class Config:
        from_attributes = True

class ExtractedStatementResponse(BaseModel):
    document: DocumentResponse
    account: Optional[AccountResponse] = None
    bank_statement_data: Optional[BankStatementDataResponse] = None
    transactions: List[TransactionResponse] = Field(default_factory=list)

class TransactionListResponse(BaseModel):
    total: int
    transactions: List[TransactionResponse]

class TransactionUpdateRequest(BaseModel):
    """
    Schema for manually updating an existing transaction.
    Most fields are optional to allow partial updates (PATCH style).
    """
    category: Optional[str] = None
    category_id: Optional[int] = None
    merchant_id: Optional[uuid.UUID] = None
    narration: Optional[str] = None
    classification: Optional[str] = None
