from pydantic import BaseModel
from typing import Optional

CATEGORY_NAMES = {
    1: "Identity, KYB & Authority",
    2: "Registration, Legal Structure & Government Recognition",
    3: "Tax & Statutory Compliance",
    4: "Financial & Banking",
    5: "Licenses, Permits & Regulatory Approvals",
    6: "Certifications, Accreditations & Independent Assurance",
    7: "Ownership, Governance & Capital",
    8: "Contracts, IP & Legal Obligations",
    9: "Others / Unclassified"
}

class DocumentClassificationResult(BaseModel):
    primary_category_id: int
    primary_category_name: str
    document_type: str
    confidence_score: float
    method: str
