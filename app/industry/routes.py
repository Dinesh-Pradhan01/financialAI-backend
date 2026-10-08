import os
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel
from app.ai.llm import PeerValuationSchema
from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["industry"])

EMPLOYEE_COUNT = 10000

class MetricValueSchema(BaseModel):
    value: Optional[float]
    period_label: Optional[str]
    basis: Optional[str]

class KeyMetricsSchema(BaseModel):
    ttm_revenue: MetricValueSchema
    latest_quarter_revenue: MetricValueSchema
    expenditure_to_revenue_pct: MetricValueSchema
    net_profit_margin_pct: MetricValueSchema

class FinancialPeriodRowSchema(BaseModel):
    period_label: str
    period_end: Optional[str]
    revenue: Optional[float]
    other_income: Optional[float]
    total_income: Optional[float]
    expenditure: Optional[float]
    interest: Optional[float]
    operating_profit: Optional[float]
    net_profit: Optional[float]
    opm_pct: Optional[float]
    npm_pct: Optional[float]

class AnnualFinancialRowSchema(FinancialPeriodRowSchema):
    basis: str

class FinancialMetaSchema(BaseModel):
    source: str
    fiscal_year_end: Optional[int]
    fiscal_year_end_assumed: bool
    quarters_available: int

class CompanyFinancialsResponseSchema(BaseModel):
    company_id: int
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    as_of: Optional[str]
    latest_period: Optional[str]
    unit: str
    financial_status: str
    reason: Optional[str]
    key_metrics: KeyMetricsSchema
    quarterly: List[FinancialPeriodRowSchema]
    annual: List[AnnualFinancialRowSchema]
    annual_status: str
    meta: FinancialMetaSchema

class AnchorCompanySchema(BaseModel):
    company_name: str
    cin: Optional[str]
    industry: str
    description: str
    listing_status: Literal["unlisted", "listed"]
    financial_status: Literal["available", "unavailable"]
    reason: Optional[str]

class CompetitorItemSchema(BaseModel):
    company_id: int
    company_name: str
    ticker: str
    overlap_level: Literal["Very High", "High", "Moderate High", "Moderate"]
    overlap_rank: int
    overlap_summary: str
    overlap_source: Literal["curated", "ai_assessed"]
    has_financials: bool
    latest_period: Optional[str]

class CompetitorsResponseSchema(BaseModel):
    status: Literal["ready", "generating", "none"]
    generated_at: Optional[str]
    anchor: AnchorCompanySchema
    competitors: List[CompetitorItemSchema]

def format_fiscal_period(period_str: str, is_quarterly: bool, fye: int = 3) -> str:
    if not period_str: return ""
    clean_str = period_str.strip().split('\n')[0].strip()
    parts = clean_str.split()
    if len(parts) < 2: return clean_str
    
    month_name = parts[0][:3].title()
    try:
        year_int = int(parts[1])
    except ValueError:
        return clean_str
        
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, 
              "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    if month_name not in months:
        return clean_str
        
    month = months[month_name]
    start_month = (fye % 12) + 1
    months_elapsed = (month - start_month) % 12
    quarter = (months_elapsed // 3) + 1
    
    if month <= fye:
        fy = year_int
    else:
        fy = year_int + 1
        
    fy_str = str(fy)[-2:]
    return f"Q{quarter} FY{fy_str}" if is_quarterly else f"FY{fy_str}"

def normalize_name(name: str) -> str:
    name = name.replace(".json", "")
    name = name.replace("_", "").replace(" ", "").replace("-", "").replace("&", "and").lower()
    return name

def parse_quarter(q_name: str) -> datetime:
    try:
        return datetime.strptime(q_name.strip(), "%b %Y")
    except ValueError:
        try:
            return datetime.strptime(q_name.strip(), "%b %y")
        except ValueError:
            return datetime.min

def to_float(val: Any, default: Any = None) -> Any:
    if val is None:
        return default
    return float(val)

@router.get("/similar-companies")
async def get_similar_companies(
    request: Request,
    company_name: str = None,
    business_category: str = None,
    primary_product_service: str = None,
    description: str = None,
    cin: str = None,
    employees: str = None,
    db: AsyncSession = Depends(get_db)
):
    from app.ai.llm import gemini_service
    import urllib.request
    import json
    import asyncio
    import yfinance as yf
    
    if not (company_name and business_category and primary_product_service and cin and employees):
        session_token = request.cookies.get("session")
        if session_token:
            from app.auth.service import verify_session
            try:
                user = await verify_session(db, session_token)
                if user and user.business_id:
                    res = await db.execute(
                        text("""
                        SELECT g.company_name, g.business_category, l.business_description, g.cin, l.primary_product_service, l.number_of_employees
                        FROM general_info g
                        LEFT JOIN leadership_info l ON g.id = l.business_id
                        WHERE g.id = :biz_id
                        """),
                        {"biz_id": user.business_id}
                    )
                    row = res.fetchone()
                    if row:
                        if not company_name: company_name = row[0]
                        if not business_category: business_category = row[1]
                        if not description: description = row[2]
                        if not cin: cin = row[3]
                        if not primary_product_service: primary_product_service = row[4]
                        if not employees: employees = row[5]
            except Exception as e:
                logger.warning(f"Failed to fetch business info from session: {e}")

    if not company_name: company_name = "Unknown Company"
    if not business_category: business_category = "General"
    if not primary_product_service: primary_product_service = "Unknown"
    if not description: description = "No description provided."
    if not employees: employees = "50"

    # 1. Fetch Taxonomy Rows
    try:
        class_res = await db.execute(text("SELECT id, sector, industry, basic_industry FROM classifications"))
        taxonomy_rows = "ID | Sector | Industry | Basic Industry\n"
        for r in class_res.fetchall():
            taxonomy_rows += f"{r[0]} | {r[1]} | {r[2]} | {r[3]}\n"
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to fetch classifications taxonomy: {e}")
        taxonomy_rows = ""

    # 2. Run Prompt 1: Get Target Classifications
    ai_result = await gemini_service.get_target_classification_ids(
        company_name=company_name,
        business_category=business_category, 
        primary_product_service=primary_product_service,
        description=description,
        employees=str(employees),
        taxonomy_rows=taxonomy_rows
    )

    if not ai_result or not ai_result.get("matched_classification_ids"):
        return {
            "status": "none",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "anchor": {
                "company_name": company_name,
                "cin": cin,
                "industry": "Unknown",
                "description": description,
                "listing_status": "unlisted",
                "financial_status": "unavailable",
                "reason": "No classifications found or AI service unavailable."
            },
            "competitors": []
        }

    matched_ids = ai_result["matched_classification_ids"]
    sector_name = ai_result.get("primary_basic_industry", "Unknown Sector")
    scale_tier = ai_result.get("scale_tier", "SME")

    # 1. Define market cap ceiling based on scale tier
    cap_limits = {
        "MICRO": 500.0,       # Max ₹500 Cr
        "SME": 1500.0,        # Max ₹1,500 Cr
        "MID_CAP": 5000.0,    # Max ₹5,000 Cr
        "LARGE_CAP": 500000.0 # Uncapped
    }
    max_cap = cap_limits.get(scale_tier, 1500.0)

    # 2. Generate embedding for MSME search context
    msme_text_blob = f"{company_name} - {business_category} - {primary_product_service} - {description}"
    query_vector = await gemini_service.generate_embedding(msme_text_blob)

    # 3. Hybrid SQL Query: Industry match + Scale ceiling + Vector similarity sort
    candidate_peers = []
    try:
        if matched_ids:
            peers_res = await db.execute(
                text("""
                SELECT 
                    c.id AS company_id, 
                    lc.company_name, 
                    lc.nse_symbol AS ticker, 
                    COALESCE(lc.market_cap_cr, 0.0) AS market_cap_cr, 
                    COALESCE(lc.ttm_revenue_cr, 0.0) AS ttm_revenue_cr, 
                    COALESCE(cls.basic_industry, 'Unknown') AS basic_industry,
                    COALESCE(lc.business_summary, 'No summary available.') AS business_summary,
                    COALESCE((e.embedding <=> :query_vector), 1.0) AS similarity_score
                FROM companies c
                JOIN listed_companies lc ON c.nse_symbol = lc.nse_symbol
                LEFT JOIN company_embeddings e ON lc.company_id = e.company_id
                LEFT JOIN classifications cls ON c.classification_id = cls.id
                WHERE c.classification_id = ANY(:ids) 
                  AND c.nse_symbol IS NOT NULL
                  AND (c.market_cap_cr <= :max_cap OR c.market_cap_cr IS NULL)
                ORDER BY similarity_score ASC
                LIMIT 20
                """),
                {
                    "ids": matched_ids, 
                    "max_cap": max_cap,
                    "query_vector": str(query_vector)
                }
            )
            for row in peers_res.fetchall():
                candidate_peers.append({
                    "company_id": int(row[0]) if row[0] else None,
                    "company_name": str(row[1]) if row[1] else "",
                    "ticker": str(row[2]) if row[2] else "",
                    "market_cap_cr": float(row[3]) if row[3] else 0.0,
                    "ttm_revenue_cr": float(row[4]) if row[4] else 0.0,
                    "basic_industry": str(row[5]) if row[5] else "",
                    "business_summary": str(row[6]) if row[6] else "",
                    "similarity_score": float(row[7]) if row[7] else 1.0
                })
            
            # Fallback widening: If scale ceiling was too aggressive and returned < 3 peers, loosen the cap
            if len(candidate_peers) < 3:
                fallback_res = await db.execute(
                    text("""
                    SELECT 
                        c.id AS company_id, 
                        lc.company_name, 
                        lc.nse_symbol AS ticker, 
                        COALESCE(lc.market_cap_cr, 0.0) AS market_cap_cr, 
                        COALESCE(lc.ttm_revenue_cr, 0.0) AS ttm_revenue_cr, 
                        COALESCE(cls.basic_industry, 'Unknown') AS basic_industry,
                        COALESCE(lc.business_summary, 'No summary available.') AS business_summary,
                        COALESCE((e.embedding <=> :query_vector), 1.0) AS similarity_score
                    FROM companies c
                    LEFT JOIN company_embeddings e ON c.id = e.company_id
                    JOIN listed_companies lc ON c.nse_symbol = lc.nse_symbol
                    LEFT JOIN classifications cls ON c.classification_id = cls.id
                    WHERE c.classification_id = ANY(:ids) AND c.nse_symbol IS NOT NULL
                    ORDER BY similarity_score ASC
                    LIMIT 20
                    """),
                    {"ids": matched_ids, "query_vector": str(query_vector)}
                )
                candidate_peers = []
                for row in fallback_res.fetchall():
                    candidate_peers.append({
                        "company_id": int(row[0]) if row[0] else None,
                        "company_name": str(row[1]) if row[1] else "",
                        "ticker": str(row[2]) if row[2] else "",
                        "market_cap_cr": float(row[3]) if row[3] else 0.0,
                        "ttm_revenue_cr": float(row[4]) if row[4] else 0.0,
                        "basic_industry": str(row[5]) if row[5] else "",
                        "business_summary": str(row[6]) if row[6] else "",
                        "similarity_score": float(row[7]) if row[7] else 1.0
                    })
    except Exception as e:
        await db.rollback()
        logger.warning(f"Database error during hybrid peer retrieval: {e}")
        # If the vector query fails, attempt a simpler SQL LIKE search as a last resort
        if matched_ids and not candidate_peers:
            try:
                logger.info("Falling back to LIKE-based peer search...")
                like_res = await db.execute(
                    text("""
                    SELECT 
                        c.id AS company_id, 
                        lc.company_name, 
                        lc.nse_symbol AS ticker, 
                        COALESCE(lc.market_cap_cr, 0.0) AS market_cap_cr, 
                        COALESCE(lc.ttm_revenue_cr, 0.0) AS ttm_revenue_cr, 
                        COALESCE(cls.basic_industry, 'Unknown') AS basic_industry,
                        COALESCE(lc.business_summary, 'No summary available.') AS business_summary,
                        1.0 AS similarity_score
                    FROM companies c
                    JOIN listed_companies lc ON c.nse_symbol = lc.nse_symbol
                    LEFT JOIN company_embeddings e ON lc.company_id = e.company_id
                    LEFT JOIN classifications cls ON c.classification_id = cls.id
                    WHERE c.classification_id = ANY(:ids) 
                      AND c.nse_symbol IS NOT NULL
                      AND (c.market_cap_cr <= :max_cap OR c.market_cap_cr IS NULL)
                    LIMIT 20
                    """),
                    {"ids": matched_ids, "max_cap": max_cap}
                )
                for row in like_res.fetchall():
                    candidate_peers.append({
                        "company_id": int(row[0]) if row[0] else None,
                        "company_name": str(row[1]) if row[1] else "",
                        "ticker": str(row[2]) if row[2] else "",
                        "market_cap_cr": float(row[3]) if row[3] else 0.0,
                        "ttm_revenue_cr": float(row[4]) if row[4] else 0.0,
                        "basic_industry": str(row[5]) if row[5] else "",
                        "business_summary": str(row[6]) if row[6] else "",
                        "similarity_score": float(row[7]) if row[7] else 1.0
                    })
            except Exception as like_e:
                await db.rollback()
                logger.error(f"LIKE-based fallback failed: {like_e}")

    # Remove duplicates
    unique_peers = []
    seen = set()
    for cp in candidate_peers:
        if cp["ticker"] not in seen:
            seen.add(cp["ticker"])
            unique_peers.append(cp)
    candidate_peers = unique_peers[:20]

    if not candidate_peers:
        logger.warning("No peers found for matched classification IDs. Returning empty.")
        return {
            "status": "none",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "anchor": {
                "company_name": company_name,
                "cin": cin,
                "industry": sector_name,
                "description": description,
                "listing_status": "unlisted",
                "financial_status": "unavailable",
                "reason": "No peers found in database."
            },
            "competitors": []
        }

    anchor_ticker = candidate_peers[0]["ticker"]

    # 4. Run Prompt 2: Ruthless M&A Analyst
    json_list_of_database_peers = json.dumps(candidate_peers, indent=2, default=str)
    
    ai_response = await gemini_service.get_top_competitors_from_peers(
        company_name=company_name,
        business_category=business_category,             
        primary_product_service=primary_product_service, 
        business_description=description,
        employees=str(employees),
        scale_tier=scale_tier,                           
        json_list_of_database_peers=json_list_of_database_peers
    )

    if not ai_response:
        return {
            "status": "none",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "anchor": {
                "company_name": company_name,
                "cin": cin,
                "industry": sector_name,
                "description": description,
                "listing_status": "unlisted",
                "financial_status": "unavailable",
                "reason": "AI ranking failed."
            },
            "competitors": []
        }

    target_summary = ai_response.get("target_summary", "No summary provided.")
    top_competitors_ai = ai_response.get("top_competitors", [])

    anchor = {
        "company_name": company_name,
        "cin": cin,
        "industry": sector_name,
        "description": description,
        "listing_status": "unlisted",
        "financial_status": "unavailable",
        "reason": target_summary
    }

    competitors = []
    for c in top_competitors_ai:
        c_dict = c if isinstance(c, dict) else c.dict()
        competitors.append({
            "company_id": c_dict.get("company_id", 0),
            "company_name": c_dict.get("company_name", ""),
            "ticker": c_dict.get("ticker", ""),
            "overlap_level": c_dict.get("peer_fit_confidence", "Moderate"),
            "overlap_rank": c_dict.get("similarity_rank", 0),
            "overlap_summary": c_dict.get("reasoning", ""),
            "overlap_source": "ai_assessed",
            "has_financials": True,
            "latest_period": None
        })

    return {
        "status": "ready",
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "anchor": anchor,
        "competitors": competitors
    }

@router.get("/company/competitors/{company_id}/financials", response_model=CompanyFinancialsResponseSchema)
async def get_company_financials(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Serves both quarterly and annual financials in one payload.
    """
    try:
        fye_res = await db.execute(
            text("""
                SELECT lc.company_name, c.nse_symbol, lc.fiscal_year_end 
                FROM companies c
                LEFT JOIN listed_companies lc ON c.nse_symbol = lc.nse_symbol
                WHERE c.id = :id 
                   OR c.nse_symbol = (SELECT nse_symbol FROM listed_companies WHERE company_id = :id LIMIT 1)
                LIMIT 1
            """),
            {"id": company_id}
        )
        fye_row = fye_res.fetchone()
        
        company_name = fye_row[0] if fye_row else None
        ticker = fye_row[1] if fye_row else None
        fye = fye_row[2] if fye_row and fye_row[2] else 3
        
        q_res = await db.execute(
            text("""
            SELECT quarter, revenue, expenditure, profit, operating_profit, other_income, interest, total_income, npm_percentage
            FROM quarterly_financials
            WHERE company_id IN (
                :id,
                (SELECT lc.company_id FROM listed_companies lc JOIN companies c ON lc.nse_symbol = c.nse_symbol WHERE c.id = :id LIMIT 1)
            )
            """),
            {"id": company_id}
        )
        
        def get_sort_date(period_str: str) -> datetime:
            if not period_str: return datetime.min
            clean_str = period_str.strip().split('\n')[0].strip()
            if clean_str.upper() == "TTM":
                return datetime.max
            parts = clean_str.split()
            if len(parts) >= 2:
                clean_str = f"{parts[0][:3]} {parts[1]}"
            return parse_quarter(clean_str)
        
        q_rows = q_res.fetchall()
        q_rows = sorted(q_rows, key=lambda r: get_sort_date(str(r[0]) if r[0] else ""))
        
        quarterly = []
        for row in q_rows:
            sales_val = float(row[1]) if row[1] else 0.0
            op_profit_val = float(row[4]) if row[4] else 0.0
            opm = (op_profit_val / sales_val * 100.0) if sales_val != 0 else 0.0
            
            quarterly.append({
                "period_label": format_fiscal_period(str(row[0]), is_quarterly=True, fye=fye) if row[0] else "",
                "period_end": None,
                "revenue": sales_val,
                "other_income": float(row[5]) if row[5] else 0.0,
                "total_income": float(row[7]) if row[7] else 0.0,
                "expenditure": float(row[2]) if row[2] else 0.0,
                "interest": float(row[6]) if row[6] else 0.0,
                "operating_profit": op_profit_val,
                "net_profit": float(row[3]) if row[3] else 0.0,
                "opm_pct": opm,
                "npm_pct": float(row[8]) if row[8] else 0.0,
            })
            
        a_res = await db.execute(
            text("""
            SELECT period, sales, other_income, expenditure, interest, net_profit, opm_percentage, total_income, npm_percentage
            FROM annual_financials
            WHERE company_id IN (
                :id,
                (SELECT lc.company_id FROM listed_companies lc JOIN companies c ON lc.nse_symbol = c.nse_symbol WHERE c.id = :id LIMIT 1)
            )
            """),
            {"id": company_id}
        )
        
        a_rows = a_res.fetchall()
        a_rows = sorted(a_rows, key=lambda r: get_sort_date(str(r[0]) if r[0] else ""))
        
        annual = []
        for row in a_rows:
            sales_val = float(row[1]) if row[1] else 0.0
            annual.append({
                "period_label": format_fiscal_period(str(row[0]), is_quarterly=False, fye=fye) if row[0] else "",
                "period_end": None,
                "revenue": sales_val,
                "other_income": float(row[2]) if row[2] else 0.0,
                "total_income": float(row[7]) if row[7] else 0.0,
                "expenditure": float(row[3]) if row[3] else 0.0,
                "interest": float(row[4]) if row[4] else 0.0,
                "operating_profit": sales_val * (float(row[6]) / 100.0) if row[6] else 0.0,
                "net_profit": float(row[5]) if row[5] else 0.0,
                "opm_pct": float(row[6]) if row[6] else 0.0,
                "npm_pct": float(row[8]) if row[8] else 0.0,
                "basis": "reported"
            })
            
        latest_period = quarterly[-1]["period_label"] if quarterly else None
        
        ttm_rev = sum((q.get("revenue") or 0.0) for q in quarterly[-4:]) if quarterly else 0.0
        ttm_exp = sum((q.get("expenditure") or 0.0) for q in quarterly[-4:]) if quarterly else 0.0
        exp_to_rev_pct = (ttm_exp / ttm_rev * 100.0) if ttm_rev else 0.0
        
        return {
            "company_id": company_id,
            "company_name": company_name,
            "ticker": ticker,
            "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_period": latest_period,
            "unit": "INR_CR",
            "financial_status": "available" if quarterly or annual else "unavailable",
            "reason": None,
            "key_metrics": {
                "ttm_revenue": {"value": ttm_rev, "period_label": "TTM", "basis": "rolled_up"},
                "latest_quarter_revenue": {"value": quarterly[-1].get("revenue") if quarterly else 0.0, "period_label": latest_period, "basis": "reported"},
                "expenditure_to_revenue_pct": {"value": exp_to_rev_pct, "period_label": "TTM", "basis": "rolled_up"},
                "net_profit_margin_pct": {"value": quarterly[-1].get("npm_pct") if quarterly else 0.0, "period_label": latest_period, "basis": "reported"}
            },
            "quarterly": quarterly,
            "annual": annual,
            "annual_status": "ok",
            "meta": {
                "source": "Database",
                "fiscal_year_end": fye,
                "fiscal_year_end_assumed": False,
                "quarters_available": len(quarterly)
            }
        }
    except Exception as e:
        logger.error(f"Error fetching financials for company_id {company_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch financial data: {str(e)}"
        )

@router.get("/company/competitors", response_model=CompetitorsResponseSchema)
async def get_company_competitors(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    session_token = request.cookies.get("session")
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    from app.auth.service import verify_session
    user = await verify_session(db, session_token)
    if not user or not user.business_id:
        raise HTTPException(status_code=400, detail="User or business not found")
        
    biz_id = user.business_id
    
    from app.company.routes import get_user_business, get_business_metadata
    from datetime import datetime, timedelta
    from app.business.models import Cache

    business = await get_user_business(user, db)
    cache = await get_business_metadata(business, db)

    if cache and cache.competitors_data and cache.updated_at > datetime.now() - timedelta(days=7):
        if "status" in cache.competitors_data:
            return cache.competitors_data
        
    # Generate on the fly if not cached
    data = await get_similar_companies(request, db=db)
    
    if cache:
        cache.competitors_data = data
        cache.updated_at = datetime.now()
    else:
        cache = Cache(
            business_id=biz_id,
            competitors_data=data,
            updated_at=datetime.now()
        )
        db.add(cache)
        
    await db.commit()
    
    return data

async def generate_competitors_background(biz_id):
    from app.database.connection import db_manager
    from sqlalchemy import text
    import json
    
    try:
        async with db_manager.session_factory() as db:
            res = await db.execute(
                text("""
                SELECT g.company_name, g.business_category, l.business_description, g.cin, l.primary_product_service, l.number_of_employees
                FROM general_info g
                LEFT JOIN leadership_info l ON g.id = l.business_id
                WHERE g.id = :biz_id
                """),
                {"biz_id": biz_id}
            )
            row = res.fetchone()
            if not row:
                return
                
            company_name = row[0] or "Unknown Company"
            business_category = row[1] or "General"
            description = row[2] or "No description provided."
            cin = row[3] or "N/A"
            primary_product_service = row[4] or "Unknown"
            employees = str(row[5]) if row[5] else "50"
            
            # Call get_similar_companies bypassing request
            data = await get_similar_companies(
                request=None,
                company_name=company_name,
                business_category=business_category,
                primary_product_service=primary_product_service,
                cin=cin,
                employees=employees,
                description=description,
                db=db
            )
            
            # Save cache
            from app.business.models import Cache
            from sqlalchemy import select
            from datetime import datetime

            cache_res = await db.execute(select(Cache).where(Cache.business_id == biz_id))
            cache = cache_res.scalar_one_or_none()
            if cache:
                cache.competitors_data = data
                cache.updated_at = datetime.now()
            else:
                cache = Cache(
                    business_id=biz_id,
                    competitors_data=data,
                    updated_at=datetime.now()
                )
                db.add(cache)
            await db.commit()
    except Exception as e:
        logger.error(f"Error in background competitors generation: {e}")



@router.get("/basic-industry/{basic_industry_name:path}")
async def get_basic_industry_data(basic_industry_name: str, db: AsyncSession = Depends(get_db)):
    normalized_target = normalize_name(basic_industry_name)

    # 1. Fetch all distinct basic industries to find a match
    try:
        res = await db.execute(text("SELECT id, basic_industry FROM classifications"))
        rows = res.fetchall()
    except Exception as e:
        logger.error(f"Error querying classifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}"
        )

    matched_class_id = None
    matched_basic_industry = None

    for class_id, basic_ind in rows:
        if basic_ind and normalize_name(basic_ind) == normalized_target:
            matched_class_id = class_id
            matched_basic_industry = basic_ind
            break

    if not matched_class_id:
        logger.warning(f"Basic industry not found for: {basic_industry_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Basic industry '{basic_industry_name}' not found."
        )

    # 2. Fetch companies matching the classification ID
    try:
        comp_res = await db.execute(
            text(
                "SELECT c.id, c.name, c.full_name, c.nse_symbol, c.bse_code, c.screener_url, c.bse_url, c.employee_count, "
                "c.cmp_rs, c.pe, c.market_cap_cr, c.div_yield_pct, c.net_profit_qtr_cr, c.qtr_profit_var_pct, "
                "c.sales_qtr_cr, c.qtr_sales_var_pct, c.roce_pct "
                "FROM companies c "
                "WHERE c.classification_id = :class_id"
            ),
            {"class_id": matched_class_id}
        )
        companies_rows = comp_res.fetchall()
    except Exception as e:
        logger.error(f"Error querying companies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}"
        )

    companies_dict = {}
    company_ids = []
    for row in companies_rows:
        c_id = row[0]
        company_ids.append(c_id)
        companies_dict[c_id] = {
            "id": c_id,
            "name": row[1],
            "full_name": row[2],
            "nse_symbol": row[3],
            "bse_code": row[4],
            "url": row[5],
            "bse_url": row[6],
            "employee_count": row[7],
            "cmp_rs": to_float(row[8]),
            "pe": to_float(row[9]),
            "market_cap_cr": to_float(row[10]),
            "div_yield_pct": to_float(row[11]),
            "net_profit_qtr_cr": to_float(row[12]),
            "qtr_profit_var_pct": to_float(row[13]),
            "sales_qtr_cr": to_float(row[14]),
            "qtr_sales_var_pct": to_float(row[15]),
            "roce_pct": to_float(row[16]),
            "quarterly_financials": []
        }

    # 3. Fetch quarterly financials for companies
    if company_ids:
        try:
            q_res = await db.execute(
                text(
                    "SELECT company_id, quarter, revenue, expenditure, profit, operating_profit "
                    "FROM quarterly_financials WHERE company_id = ANY(:ids)"
                ),
                {"ids": list(company_ids)}
            )
            for q_row in q_res.fetchall():
                c_id = q_row[0]
                q_data = {
                    "quarter": q_row[1],
                    "revenue": to_float(q_row[2]),
                    "expenditure": to_float(q_row[3]),
                    "profit": to_float(q_row[4]),
                    "operating_profit": to_float(q_row[5])
                }
                companies_dict[c_id]["quarterly_financials"].append(q_data)
        except Exception as e:
            logger.error(f"Error querying quarterly financials: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database query error: {str(e)}"
            )

    # Sort financials chronologically
    for comp in companies_dict.values():
        comp["quarterly_financials"].sort(key=lambda q: parse_quarter(q["quarter"]))

    companies = list(companies_dict.values())
    companies.sort(key=lambda c: c.get("market_cap_cr") or 0.0, reverse=True)
    for idx, comp in enumerate(companies, 1):
        comp["s_no"] = idx

    # 1. Inject employee count and calculate revenue per employee for all companies
    for company in companies:
        company["employee_count"] = EMPLOYEE_COUNT
        sales = company.get("sales_qtr_cr")
        sales = sales if sales is not None else 0.0
        company["revenue_per_employee"] = (sales * 10000000.0) / EMPLOYEE_COUNT if sales else 0.0

    # 2. Sort by market cap to identify top 10 companies
    sorted_companies = sorted(
        companies, 
        key=lambda c: c.get("market_cap_cr", 0.0) if c.get("market_cap_cr") is not None else 0.0, 
        reverse=True
    )
    top_10 = sorted_companies[:10]

    # 3. Calculate quarterly average for top 10 companies
    quarters_data: List[Dict[str, Any]] = []
    
    if top_10 and top_10[0].get("quarterly_financials"):
        standard_quarters = [q.get("quarter") for q in top_10[0]["quarterly_financials"]]
        num_quarters = len(standard_quarters)

        for i in range(num_quarters):
            q_name = standard_quarters[i]
            q_revs = []
            q_exps = []
            q_profits = []
            
            for c in top_10:
                q_fin = c.get("quarterly_financials", [])
                if i < len(q_fin):
                    rev_val = q_fin[i].get("revenue")
                    q_revs.append(rev_val if rev_val is not None else 0.0)
                    
                    exp_val = q_fin[i].get("expenditure")
                    q_exps.append(exp_val if exp_val is not None else 0.0)
                    
                    prof_val = q_fin[i].get("profit")
                    q_profits.append(prof_val if prof_val is not None else 0.0)
            
            avg_rev = sum(q_revs) / len(q_revs) if q_revs else 0.0
            avg_exp = sum(q_exps) / len(q_exps) if q_exps else 0.0
            avg_prof = sum(q_profits) / len(q_profits) if q_profits else 0.0
            
            quarters_data.append({
                "quarter": q_name,
                "revenue": avg_rev,
                "expenditure": avg_exp,
                "profit": avg_prof
            })

    # 4. Generate dynamic MSME quarterly financials by scaling peer averages
    msme_financials = []
    if quarters_data:
        scale_factor = 500.0
        multipliers = [1.02, 0.96, 1.04, 0.98, 1.01]
        
        for idx, q in enumerate(quarters_data):
            mult = multipliers[idx % len(multipliers)]
            raw_rev = (q["revenue"] / scale_factor) * mult
            raw_exp = (q["expenditure"] / scale_factor) * (2.0 - mult)
            raw_prof = (q["profit"] / scale_factor) * (mult * 1.08)
            
            msme_financials.append({
                "quarter": q["quarter"],
                "revenue": max(0.01, round(raw_rev, 2)),
                "expenditure": max(0.01, round(raw_exp, 2)),
                "profit": max(0.01, round(raw_prof, 2))
            })

    msme_data = {
        "company_name": "Your MSME",
        "employee_count": EMPLOYEE_COUNT,
        "revenue_per_employee": (msme_financials[-1]["revenue"] * 10000000.0) / EMPLOYEE_COUNT if msme_financials else 0.0,
        "quarterly_financials": msme_financials
    }

    # 5. Compute QoQ Growth Trends for Line Charts
    peer_growth_trends = []
    msme_growth_trends = []
    
    for i in range(1, len(quarters_data)):
        prev_peer = quarters_data[i-1]
        curr_peer = quarters_data[i]
        
        peer_rev_g = ((curr_peer["revenue"] - prev_peer["revenue"]) / prev_peer["revenue"] * 100.0) if prev_peer["revenue"] else 0.0
        peer_prof_g = ((curr_peer["profit"] - prev_peer["profit"]) / prev_peer["profit"] * 100.0) if prev_peer["profit"] else 0.0
        peer_exp_g = ((curr_peer["expenditure"] - prev_peer["expenditure"]) / prev_peer["expenditure"] * 100.0) if prev_peer["expenditure"] else 0.0

        prev_msme = msme_financials[i-1]
        curr_msme = msme_financials[i]

        msme_rev_g = ((curr_msme["revenue"] - prev_msme["revenue"]) / prev_msme["revenue"] * 100.0) if prev_msme["revenue"] else 0.0
        msme_prof_g = ((curr_msme["profit"] - prev_msme["profit"]) / prev_msme["profit"] * 100.0) if prev_msme["profit"] else 0.0
        msme_exp_g = ((curr_msme["expenditure"] - prev_msme["expenditure"]) / prev_msme["expenditure"] * 100.0) if prev_msme["expenditure"] else 0.0

        label = f"Q{i}"
        
        peer_growth_trends.append({
            "quarter_label": label,
            "quarter_name": curr_peer["quarter"],
            "revenue_growth": round(peer_rev_g, 2),
            "profit_growth": round(peer_prof_g, 2),
            "expenditure_growth": round(peer_exp_g, 2)
        })

        msme_growth_trends.append({
            "quarter_label": label,
            "quarter_name": curr_msme["quarter"],
            "revenue_growth": round(msme_rev_g, 2),
            "profit_growth": round(msme_prof_g, 2),
            "expenditure_growth": round(msme_exp_g, 2)
        })

    return {
        "basic_industry_name": basic_industry_name.replace(".json", ""),
        "companies": companies,
        "msme_data": msme_data,
        "top_5_avg_financials": quarters_data,
        "peer_growth_trends": peer_growth_trends,
        "msme_growth_trends": msme_growth_trends
    }

@router.get("/stocks/top5")
async def get_top_5_stocks(
    request: Request,
    basic_industry: str = None,
    db: AsyncSession = Depends(get_db)
):
    default_symbols = ["ADANIENT.BO", "ULTRACEMCO.BO", "JSWSTEEL.BO", "TATASTEEL.NS", "HINDZINC.NS"]
    symbols = default_symbols
    
    explicit_param = bool(basic_industry)
    
    if not basic_industry:
        # 1. Try to get industry from current session cookie
        session_token = request.cookies.get("session")
        if session_token:
            from app.auth.service import verify_session
            try:
                user = await verify_session(db, session_token)
                if user and user.business_id:
                    res = await db.execute(
                        text("SELECT business_category FROM general_info WHERE id = :biz_id"),
                        {"biz_id": user.business_id}
                    )
                    row = res.fetchone()
                    if row and row[0]:
                        basic_industry = row[0]
            except Exception as e:
                logger.warning(f"Failed to fetch industry from session: {e}")

        # 2. Try to get industry from latest business onboarding category in database
        if not basic_industry:
            try:
                res = await db.execute(
                    text("SELECT business_category FROM general_info WHERE business_category IS NOT NULL ORDER BY updated_at DESC LIMIT 1")
                )
                row = res.fetchone()
                if row and row[0]:
                    basic_industry = row[0]
            except Exception as e:
                logger.warning(f"Failed to fetch fallback industry from general_info: {e}")

    if basic_industry:
        try:
            # Fetch basic industry data from the industry API handler internally
            industry_data = await get_basic_industry_data(basic_industry_name=basic_industry, db=db)
            
            # Extract top 5 companies by market cap
            top_companies = industry_data.get("companies", [])[:5]
            
            # Build list of potential symbols
            industry_symbols = []
            for comp in top_companies:
                nse_sym = comp.get("nse_symbol")
                bse_cd = comp.get("bse_code")
                if nse_sym:
                    industry_symbols.extend([f"{nse_sym}.NS", f"{nse_sym}.BO"])
                if bse_cd:
                    bse_str = str(bse_cd).strip()
                    if bse_str:
                        industry_symbols.extend([f"{bse_str}.BO", f"{bse_str}.NS"])
            
            found_symbols = []
            if industry_symbols:
                # Query stock_prices to see which of these potential symbols actually exist
                price_syms_res = await db.execute(
                    text("SELECT DISTINCT symbol FROM stock_prices WHERE symbol = ANY(:symbols)"),
                    {"symbols": list(industry_symbols)}
                )
                found_symbols = [r[0] for r in price_syms_res.fetchall()]
                
            if found_symbols:
                symbols = found_symbols
            else:
                if explicit_param:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"No stock price data available for basic industry '{basic_industry}'."
                    )
                else:
                    logger.warning(f"No stock price data available for automatically-derived basic industry '{basic_industry}'. Falling back to default list.")
                    symbols = default_symbols
                    
        except HTTPException as he:
            if explicit_param:
                raise he
            else:
                logger.warning(f"Failed to fetch basic industry '{basic_industry}' internally (Status {he.status_code}): {he.detail}. Falling back to default list.")
                symbols = default_symbols
        except Exception as e:
            logger.error(f"Error fetching basic industry internally: {e}")
            if explicit_param:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to resolve basic industry: {str(e)}"
                )
            else:
                logger.warning(f"Error fetching basic industry '{basic_industry}' internally. Falling back to default list.")
                symbols = default_symbols

    try:
        res = await db.execute(
            text(
                "SELECT symbol, price_date, price "
                "FROM stock_prices "
                "WHERE symbol = ANY(:symbols) "
                "ORDER BY price_date ASC"
            ),
            {"symbols": list(symbols)}
        )
        rows = res.fetchall()
    except Exception as e:
        logger.error(f"Error querying stock prices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load stock price data: {str(e)}"
        )

    # Reconstruct dictionary mapping date_str -> symbol -> price
    from collections import defaultdict
    data = defaultdict(dict)
    for row in rows:
        sym = row[0]
        date_str = row[1].strftime("%Y-%m-%d") if hasattr(row[1], 'strftime') else str(row[1])
        price = to_float(row[2])
        data[date_str][sym] = price
        
    return dict(data)


@router.get("/basic-industries")
async def get_all_basic_industries(db: AsyncSession = Depends(get_db)):
    try:
        res = await db.execute(
            text(
                "SELECT DISTINCT cl.basic_industry "
                "FROM classifications cl "
                "JOIN companies c ON c.classification_id = cl.id "
                "ORDER BY cl.basic_industry ASC"
            )
        )
        return [r[0] for r in res.fetchall() if r[0]]
    except Exception as e:
        logger.error(f"Error querying basic industries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}"
        )

@router.get("/classifications")
async def get_all_classifications(db: AsyncSession = Depends(get_db)):
    try:
        res = await db.execute(
            text(
                "SELECT id, macro_economic_indicator, sector, industry, basic_industry "
                "FROM classifications "
                "ORDER BY macro_economic_indicator, sector, industry, basic_industry ASC"
            )
        )
        return [
            {
                "id": r[0],
                "macro_economic_indicator": r[1],
                "sector": r[2],
                "industry": r[3],
                "basic_industry": r[4]
            }
            for r in res.fetchall()
        ]
    except Exception as e:
        logger.error(f"Error querying classifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}"
        )



