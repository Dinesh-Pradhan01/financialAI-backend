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
    business = None
    if user.business_id:
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
        contact_person=info.founder_ceo_name if info else None,
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


