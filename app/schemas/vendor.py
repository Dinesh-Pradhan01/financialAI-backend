from typing import Optional, List
import re
from datetime import date
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, UUID4

class VendorBase(BaseModel):
    vendor_id: str
    vendor_name: str
    legal_name: Optional[str] = None
    entity_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    industry: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    cin_number: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    contract_id: Optional[str] = None
    project_name: Optional[str] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date] = None
    contract_end_date: Optional[date] = None
    renewal_date: Optional[date] = None
    contract_value: Optional[float] = None
    currency: Optional[str] = None
    base_cost: Optional[float] = None
    support_cost: Optional[float] = None
    maintenance_cost: Optional[float] = None
    hosting_cost: Optional[float] = None
    cloud_cost: Optional[float] = None
    miscellaneous_cost: Optional[float] = None
    tax_percentage: Optional[float] = None
    discount: Optional[float] = None
    payment_flow: Optional[str] = None
    expected_billing: Optional[float] = None
    payment_type: Optional[str] = None
    frequency: Optional[str] = None
    recurring: Optional[bool] = None
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    branch_name: Optional[str] = None
    primary_account: Optional[bool] = None
    status: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v == "":
            return None
        return v

class VendorCreate(VendorBase):
    @field_validator("gst_number")
    @classmethod
    def validate_gst(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", v):
            raise ValueError("Invalid GST format")
        return v

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", v):
            raise ValueError("Invalid PAN format")
        return v

    @field_validator("cin_number")
    @classmethod
    def validate_cin(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$", v):
            raise ValueError("Invalid CIN format")
        return v

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
            raise ValueError("Invalid IFSC code")
        return v

class VendorUpdate(VendorBase):
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None

    @field_validator("gst_number")
    @classmethod
    def validate_gst(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", v):
            raise ValueError("Invalid GST format")
        return v

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", v):
            raise ValueError("Invalid PAN format")
        return v

    @field_validator("cin_number")
    @classmethod
    def validate_cin(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$", v):
            raise ValueError("Invalid CIN format")
        return v

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
    records: list[VendorCreate]
    summary: dict
    upload_id: Optional[str] = None
    schema_def: Optional[dict] = None
