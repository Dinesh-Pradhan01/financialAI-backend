import uuid
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class GeneralInfoSaveSchema(BaseModel):
    company_name: str = Field(..., min_length=2)
    business_category: str
    business_type: str
    cin: Optional[str] = None
    gstin: Optional[str] = None
    business_pan: str = Field(..., min_length=10, max_length=10)
    udyam_number: Optional[str] = None
    date_of_incorporation: Optional[date] = None
    registered_address: str = Field(..., min_length=5)
    operational_address: Optional[str] = None
    state: str
    city: str
    pincode: str
    website: Optional[str] = None
    official_email: EmailStr
    official_phone: str = Field(..., min_length=10)

class GeneralInfoResponseSchema(BaseModel):
    company_name: str
    business_category: str
    business_type: str
    cin: Optional[str] = None
    gstin: Optional[str] = None
    business_pan: str
    udyam_number: Optional[str] = None
    date_of_incorporation: Optional[date] = None
    registered_address: str
    operational_address: Optional[str] = None
    state: str
    city: str
    pincode: str
    website: Optional[str] = None
    official_email: str
    official_phone: str

class LeadershipInfoSaveSchema(BaseModel):
    founder_ceo_name: Optional[str] = None
    primary_contact_person: str = Field(..., min_length=2)
    designation: Optional[str] = None
    years_in_business: Optional[str] = None
    number_of_employees: Optional[str] = None
    number_of_branches: Optional[str] = None
    business_model: Optional[str] = None
    primary_product_service: Optional[str] = None
    business_description: Optional[str] = None

class LeadershipInfoResponseSchema(BaseModel):
    founder_ceo_name: Optional[str] = None
    primary_contact_person: str
    designation: Optional[str] = None
    years_in_business: Optional[str] = None
    number_of_employees: Optional[str] = None
    number_of_branches: Optional[str] = None
    business_model: Optional[str] = None
    primary_product_service: Optional[str] = None
    business_description: Optional[str] = None


class FinancialInfoSaveSchema(BaseModel):
    primary_bank: Optional[str] = None
    number_of_accounts: Optional[int] = None
    has_business_loan: Optional[bool] = None
    has_business_credit_card: Optional[bool] = None
    accounting_software: Optional[str] = None
    digital_payment_methods: Optional[List[str]] = Field(default_factory=list)


class DocumentResponseSchema(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    document_type: str
    document_category: str
    filename: str
    original_name: str
    file_size_bytes: int
    mime_type: str
    upload_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessOnboardingFullResponse(BaseModel):
    business_id: Optional[uuid.UUID] = None
    current_step: int = 1
    completion_percentage: float = 0.0
    onboarding_completed: bool = False
    general_info: Optional[GeneralInfoResponseSchema] = None
    leadership_info: Optional[LeadershipInfoResponseSchema] = None
    financial_info: Optional[FinancialInfoSaveSchema] = None
    verification_status: str = "pending"
    documents: List[DocumentResponseSchema] = Field(default_factory=list)
