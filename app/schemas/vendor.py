from typing import Optional, List
import re
from datetime import date
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, UUID4

class VendorBase(BaseModel):
    vendor_id: str
    vendor_name: str
    category: str
    contract_id: str
    contract_value: float
    monthly_cost: float
    frequency: str
    bank_name: str
    account_holder_name: str
    account_number: str
    ifsc_code: str

    legal_name: Optional[str] = None
    industry: Optional[str] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    currency: Optional[str] = None
    payment_type: Optional[str] = None
    recurring: Optional[str] = None
    status: Optional[str] = None

class VendorCreate(VendorBase):
    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
            raise ValueError("Invalid IFSC code")
        return v

class VendorUpdate(BaseModel):
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    contract_id: Optional[str] = None
    contract_value: Optional[float] = None
    currency: Optional[str] = None
    monthly_cost: Optional[float] = None
    payment_type: Optional[str] = None
    frequency: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    status: Optional[str] = None
    legal_name: Optional[str] = None
    category: Optional[str] = None
    industry: Optional[str] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    recurring: Optional[str] = None
    bank_name: Optional[str] = None

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
            raise ValueError("Invalid IFSC code")
        return v

class VendorResponse(VendorBase):
    id: UUID4

    model_config = ConfigDict(from_attributes=True)

class VendorListResponse(BaseModel):
    items: list[VendorResponse]
    total: int
    page: int
    size: int

class VendorPreview(BaseModel):
    records: list[dict]
    summary: dict
    upload_id: Optional[str] = None
    schema_def: Optional[dict] = None
