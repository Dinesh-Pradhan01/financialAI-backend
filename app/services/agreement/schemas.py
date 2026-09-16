from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import date
from enum import Enum

class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"

class AgreementDataSchema(BaseModel):
    contract_value: Optional[float] = Field(default=None, description="The total financial value of the contract. Example: 150000.0")
    currency: Optional[str] = Field(default=None, description="The 3-letter currency code (e.g., USD, INR, EUR) or symbol")
    contract_start_date: Optional[str] = Field(default=None, description="The start date of the contract in YYYY-MM-DD or DD-MM-YYYY format")
    contract_end_date: Optional[str] = Field(default=None, description="The end date of the contract in YYYY-MM-DD or DD-MM-YYYY format")
    contract_type: Optional[str] = Field(default=None, description="The type of the agreement, e.g., NDA, MSA, SOW")
    payment_terms: Optional[str] = Field(default=None, description="Payment terms, e.g., Net 30, Net 60")

class VendorAgreementSchema(AgreementDataSchema):
    pass

class ClientAgreementSchema(AgreementDataSchema):
    pass

class ValidationResult(BaseModel):
    valid: bool
    errors: List[str]
    ready_to_import: bool
