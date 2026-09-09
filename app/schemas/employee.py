from typing import Optional
import re
from datetime import date
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, UUID4

class EmployeeBase(BaseModel):
    employee_id: str
    employee_name: str
    email: EmailStr
    joining_date: str
    department: str
    designation: str
    salary: str
    account_number: str
    ifsc_code: str
    bank_name: str
    employment_type: Optional[str] = None
    status: Optional[str] = None
    salary_frequency: Optional[str] = None
    account_holder_name: Optional[str] = None
    payment_mode: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v == "":
            return None
        return v

class EmployeeCreate(EmployeeBase):
    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
            raise ValueError("Invalid IFSC code")
        return v

class EmployeeUpdate(BaseModel):
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    email: Optional[EmailStr] = None
    joining_date: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employment_type: Optional[str] = None
    status: Optional[str] = None
    salary: Optional[str] = None
    salary_frequency: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    payment_mode: Optional[str] = None

class EmployeeResponse(EmployeeBase):
    id: UUID4
    is_deleted: bool

    model_config = ConfigDict(from_attributes=True)

class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    size: int

class EmployeeRecordDTO(BaseModel):
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    email: Optional[str] = None
    joining_date: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    salary: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_name: Optional[str] = None
    employment_type: Optional[str] = None
    status: Optional[str] = None
    salary_frequency: Optional[str] = None
    account_holder_name: Optional[str] = None
    payment_mode: Optional[str] = None
    rowId: str
    sourceRow: int
    isBlank: bool

class ValidationIssue(BaseModel):
    id: str
    severity: str
    code: str
    message: str
    rowId: Optional[str] = None
    sourceRow: Optional[int] = None
    field: Optional[str] = None

class ValidationSummary(BaseModel):
    validEmployees: int
    validRecords: Optional[int] = None
    warnings: int
    errors: int
    issues: list[ValidationIssue]
    errorRowIds: list[str]
    warningRowIds: list[str]
    duplicateIds: int
    missingRequiredFields: int

class EmployeePreviewResponse(BaseModel):
    upload_id: str
    records: list[EmployeeRecordDTO]
    summary: ValidationSummary
    schema_def: Optional[dict] = None

