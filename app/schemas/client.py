from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class ClientBase(BaseModel):
    client_id: str
    client_name: str
    category: str
    legal_name: Optional[str] = None
    industry: Optional[str] = None
    contract_id: Optional[str] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date | str] = None
    contract_end_date: Optional[date | str] = None
    contract_value: Decimal | float | int
    currency: Optional[str] = None
    revenue: Decimal | float | int
    payment_type: Optional[str] = None
    frequency: str
    recurring: Optional[str] = None
    bank_name: str
    account_holder_name: str
    account_number: str
    ifsc_code: str
    status: Optional[str] = None

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(v).upper()):
            raise ValueError("Invalid IFSC code")
        return str(v).upper()


class ClientCreate(ClientBase):
    model_config = ConfigDict(from_attributes=True)


class ClientUpdate(BaseModel):
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    category: Optional[str] = None
    legal_name: Optional[str] = None
    industry: Optional[str] = None
    contract_id: Optional[str] = None
    contract_type: Optional[str] = None
    contract_start_date: Optional[date | str] = None
    contract_end_date: Optional[date | str] = None
    contract_value: Optional[Decimal | float | int] = None
    currency: Optional[str] = None
    revenue: Optional[Decimal | float | int] = None
    payment_type: Optional[str] = None
    frequency: Optional[str] = None
    recurring: Optional[str] = None
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    status: Optional[str] = None

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(v).upper()):
            raise ValueError("Invalid IFSC code")
        return str(v).upper()


class ClientPreview(BaseModel):
    records: list[dict]
    summary: dict
    upload_id: Optional[str] = None
    schema_def: Optional[dict] = None


class ClientHistorySummary(BaseModel):
    upload_id: str
    source: str
    uploaded_at: Optional[str] = None
    total_rows: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    rejected_count: int = 0


class ClientValidationError(BaseModel):
    row: Optional[int] = None
    field: str
    error: str
