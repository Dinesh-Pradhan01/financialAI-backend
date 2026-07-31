import logging
import os
import uuid
import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_session_user
from app.auth.model import User
from app.database.connection import get_db
from app.business.models import (
    GeneralInfo,
    LeadershipInfo,
    BusinessVerification,
    BusinessVerificationDocument,
)
from app.company.schemas import (
    CompanyProfileResponse,
    IndustryLeaderResponse,
    CompanyRatingResponse,
    CompanyNewsResponse,
    CompanyAIViewResponse,
    CompanyDocumentResponse,
)
from app.ai.llm import gemini_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/company", tags=["company"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "business_docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def get_user_business(user: User, db: AsyncSession) -> GeneralInfo:
    if not user.business_id:
        raise HTTPException(status_code=404, detail="User does not have an associated business.")
    
    res = await db.execute(select(GeneralInfo).where(GeneralInfo.id == user.business_id))
    business = res.scalar_one_or_none()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business profile not found.")
        
    return business

@router.get("/profile", response_model=CompanyProfileResponse)
async def get_company_profile(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    # Fetch leadership info for additional details
    info_res = await db.execute(select(LeadershipInfo).where(LeadershipInfo.business_id == business.id))
    info = info_res.scalar_one_or_none()
    
    return CompanyProfileResponse(
        company_name=business.company_name,
        industry=business.business_category, # Using category as industry
        business_type=business.business_type,
        business_category=business.business_category,
        gst=business.gstin,
        pan=business.business_pan,
        website=business.website,
        summary=info.business_description if info else None,
        registered_address=business.registered_address,
        contact_person=info.primary_contact_person if info else None,
        email=business.official_email,
        phone=business.official_phone,
        udyam_number=business.udyam_number,
    )

@router.get("/industry-leaders", response_model=List[IndustryLeaderResponse])
async def get_industry_leaders(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    # Mock data based on industry
    business = await get_user_business(current_user, db)
    industry = business.business_category.lower()
    
    leaders = []
    if "technology" in industry or "it" in industry or "software" in industry:
        leaders = [
            {"id": 1, "name": "Tata Consultancy Services (TCS)", "market_cap": "$160B"},
            {"id": 2, "name": "Infosys", "market_cap": "$80B"},
            {"id": 3, "name": "Wipro", "market_cap": "$30B"},
        ]
    elif "manufacturing" in industry:
        leaders = [
            {"id": 1, "name": "Tata Steel", "market_cap": "$20B"},
            {"id": 2, "name": "JSW Steel", "market_cap": "$25B"},
            {"id": 3, "name": "Larsen & Toubro", "market_cap": "$50B"},
        ]
    else:
        leaders = [
            {"id": 1, "name": "Reliance Industries", "market_cap": "$200B"},
            {"id": 2, "name": "HDFC Bank", "market_cap": "$150B"},
            {"id": 3, "name": "ICICI Bank", "market_cap": "$80B"},
        ]
        
    return [IndustryLeaderResponse(**l) for l in leaders]

@router.get("/rating", response_model=CompanyRatingResponse)
async def get_company_rating(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    ver_res = await db.execute(select(BusinessVerification).where(BusinessVerification.business_id == business.id))
    ver = ver_res.scalar_one_or_none()
    
    docs_res = await db.execute(select(BusinessVerificationDocument).where(BusinessVerificationDocument.business_id == business.id))
    docs = docs_res.scalars().all()
    
    # Calculate simple rating
    verification_score = 100 if (ver and ver.is_verified) else (50 if (ver and ver.verification_status == "pending") else 0)
    docs_score = min(len(docs) * 20, 100)
    
    overall = int((verification_score * 0.5) + (docs_score * 0.5))
    
    return CompanyRatingResponse(
        overall=overall,
        verification=verification_score,
        documents=docs_score,
        compliance=None, # Future
        financial_health=None # Future
    )

@router.get("/news", response_model=List[CompanyNewsResponse])
async def get_company_news(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    # Mock data
    news = [
        {
            "id": 1,
            "headline": f"{business.company_name} announces new strategic growth plans for Q3.",
            "source": "Financial Express",
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "summary": "The company revealed its expansion strategy focusing on emerging markets."
        },
        {
            "id": 2,
            "headline": f"Industry trends point to massive shifts in {business.business_category} sector.",
            "source": "Economic Times",
            "date": (datetime.datetime.now() - datetime.timedelta(days=2)).strftime("%Y-%m-%d"),
            "summary": "Analysts predict significant regulatory and technological changes affecting local businesses."
        },
        {
            "id": 3,
            "headline": f"Government introduces new subsidies for SMEs in {business.state}.",
            "source": "LiveMint",
            "date": (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d"),
            "summary": "Eligible businesses can now apply for grants to accelerate digital transformation."
        }
    ]
    return [CompanyNewsResponse(**n) for n in news]

@router.post("/ai-view", response_model=CompanyAIViewResponse)
async def generate_company_ai_view(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    info_res = await db.execute(select(LeadershipInfo).where(LeadershipInfo.business_id == business.id))
    info = info_res.scalar_one_or_none()
    
    description = info.business_description if info and info.business_description else f"A business in the {business.business_category} industry."
    
    markdown = await gemini_service.generate_company_ai_view(
        company_name=business.company_name,
        business_category=business.business_category,
        business_type=business.business_type,
        industry=business.business_category,
        description=description
    )
    
    return CompanyAIViewResponse(markdown_content=markdown)

@router.get("/documents", response_model=List[CompanyDocumentResponse])
async def get_company_documents(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    docs_res = await db.execute(select(BusinessVerificationDocument).where(BusinessVerificationDocument.business_id == business.id))
    docs = docs_res.scalars().all()
    
    return [CompanyDocumentResponse.model_validate(d, from_attributes=True) for d in docs]

@router.post("/documents", response_model=CompanyDocumentResponse)
async def upload_company_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    document_category: str = Form(...), # Expected: Financial, Compliance, Insurance, Verification, Other
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    biz_dir = os.path.join(UPLOAD_DIR, str(business.id))
    os.makedirs(biz_dir, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{document_type}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = os.path.join(biz_dir, safe_filename)
    
    file_bytes = await file.read()
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    new_doc = BusinessVerificationDocument(
        business_id=business.id,
        document_type=document_type,
        document_category=document_category,
        filename=safe_filename,
        original_name=file.filename,
        file_path=file_path,
        file_size_bytes=len(file_bytes),
        mime_type=file.content_type or "application/octet-stream",
        upload_status="uploaded",
    )
    db.add(new_doc)
    await db.flush()
    await db.refresh(new_doc)
    
    return CompanyDocumentResponse.model_validate(new_doc, from_attributes=True)

@router.delete("/documents/{doc_id}")
async def delete_company_document(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    business = await get_user_business(current_user, db)
    
    doc_res = await db.execute(
        select(BusinessVerificationDocument).where(
            BusinessVerificationDocument.id == doc_id,
            BusinessVerificationDocument.business_id == business.id
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove file {doc.file_path}: {e}")
            
    await db.delete(doc)
    await db.commit()
    
    return {"message": "Document deleted successfully"}
