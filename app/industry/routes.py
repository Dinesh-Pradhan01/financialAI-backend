import os
import json
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["industry"])

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
INDUSTRY_DIR = os.path.join(BACKEND_ROOT, "industry_data", "industry")
STOCK_PRICE_PATH = os.path.join(BACKEND_ROOT, "industry_data", "stock_price.json")

EMPLOYEE_COUNT = 10000

@router.get("/sectors/{sector_name}")
async def get_sector_data(sector_name: str):
    if not sector_name.endswith(".json"):
        file_name = f"{sector_name}.json"
    else:
        file_name = sector_name

    file_path = os.path.join(INDUSTRY_DIR, file_name)

    if not os.path.exists(file_path):
        logger.warning(f"Sector file not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sector '{sector_name}' not found."
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            companies: List[Dict[str, Any]] = json.load(f)
    except Exception as e:
        logger.error(f"Error loading sector file {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load sector data: {str(e)}"
        )

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
        "sector_name": sector_name.replace(".json", ""),
        "companies": companies,
        "msme_data": msme_data,
        "top_5_avg_financials": quarters_data,
        "peer_growth_trends": peer_growth_trends,
        "msme_growth_trends": msme_growth_trends
    }

@router.get("/stocks/top5")
async def get_top_5_stocks():
    if not os.path.exists(STOCK_PRICE_PATH):
        logger.warning(f"Stock price file not found: {STOCK_PRICE_PATH}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock price data not found."
        )
    try:
        with open(STOCK_PRICE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading stock price file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load stock price data: {str(e)}"
        )
