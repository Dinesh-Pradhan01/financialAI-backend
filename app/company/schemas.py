from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import uuid

class CompanyProfileResponse(BaseModel):
    company_name: str
    industry: str
    business_type: str
    business_category: str
    gst: Optional[str] = None
    pan: str
    website: Optional[str] = None
    summary: Optional[str] = None
    registered_address: str
    contact_person: Optional[str] = None
    email: str
    phone: str
    udyam_number: Optional[str] = None

class IndustryLeaderResponse(BaseModel):
    id: int
    name: str
    market_cap: Optional[str] = None

class CompanyRatingResponse(BaseModel):
    overall: int
    verification: int
    documents: int
    compliance: Optional[int] = None
    financial_health: Optional[int] = None

class CompanyNewsResponse(BaseModel):
    id: int
    headline: str
    source: str
    date: str
    summary: str

class CompanyAIViewRequest(BaseModel):
    company_id: uuid.UUID

class CompanyAIViewResponse(BaseModel):
    markdown_content: str

class CompanyDocumentResponse(BaseModel):
    id: uuid.UUID
    document_type: str
    document_category: str
    filename: str
    original_name: str
    file_size_bytes: int
    mime_type: str
    upload_status: str
