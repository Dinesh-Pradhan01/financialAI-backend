"""
Analysis API Routers
-------------------
FastAPI endpoints grouped under Swagger tag "Analysis" (/api/v1/analysis):
- overview
- income
- expenditure
- client (bubble & directory)
- vendor (bubble & directory)
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.auth.dependencies import get_optional_current_user
from app.auth.model import User
from app.utils.response import success_response, error_response
from app.api.spending.service import SpendingService
from app.api.spending.schemas import SpendingFullReport
from app.services.spotlite_service import SpotliteEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])


# ---------------------------------------------------------------------------
# 1. Overview Analysis Endpoint (/api/v1/analysis/overview)
# ---------------------------------------------------------------------------
@router.get(
    "/overview",
    response_model=SpendingFullReport,
    summary="Get Overview Analysis & Financial Intelligence Report",
    description="Returns complete Overview analysis including executive scorecard, header metadata, macro cash flow, and temporal patterns."
)
async def get_overview_analysis(
    user_id: Optional[str] = Query(None, description="User ID, Email, or Firebase ID to analyze for"),
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpendingService.compute_spending_report(
            db, user_id=user_id, company_name=company_name, business_id=business_id, current_user=current_user
        )
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing Overview report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Overview report: {str(e)}")


# ---------------------------------------------------------------------------
# 2. Income Analysis Endpoint (/api/v1/analysis/income)
# ---------------------------------------------------------------------------
@router.get(
    "/income",
    summary="Get Income Analysis & Credit Inflow Trajectory",
    description="Returns inward credit breakdown, monthly revenue trajectories, and income velocity metrics."
)
async def get_income_analysis(
    user_id: Optional[str] = Query(None),
    business_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpendingService.compute_spending_report(
            db, user_id=user_id, business_id=business_id, current_user=current_user
        )
        return success_response("Income analysis generated successfully", data={
            "header_metadata": report.section_1_header_metadata,
            "executive_summary": [s for s in report.executive_summary if "inflow" in s.analytical_module.lower() or "revenue" in s.key_indicator.lower() or "runway" in s.key_indicator.lower()],
            "macro_cash_flow": report.section_2_macro_cash_flow,
            "channel_distribution": report.section_4_channel_distribution,
        })
    except Exception as e:
        logger.error(f"Error fetching Income analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Income analysis: {str(e)}")


# ---------------------------------------------------------------------------
# 3. Expenditure Analysis Endpoint (/api/v1/analysis/expenditure)
# ---------------------------------------------------------------------------
@router.get(
    "/expenditure",
    summary="Get Expenditure Analysis & Debit Outflow Breakdown",
    description="Returns debit outflow breakdown, payroll vs non-payroll opex, fixed/variable split, and anomaly risk controls."
)
async def get_expenditure_analysis(
    user_id: Optional[str] = Query(None),
    business_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpendingService.compute_spending_report(
            db, user_id=user_id, business_id=business_id, current_user=current_user
        )
        return success_response("Expenditure analysis generated successfully", data={
            "header_metadata": report.section_1_header_metadata,
            "liquidity_diagnostics": report.section_2_macro_cash_flow.liquidity_diagnostics,
            "anomaly_risk": report.section_5_anomaly_risk,
            "channel_distribution": report.section_4_channel_distribution,
        })
    except Exception as e:
        logger.error(f"Error fetching Expenditure analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Expenditure analysis: {str(e)}")


# ---------------------------------------------------------------------------
# 4. Client Analytics & Bubble Network Graph Endpoints (/api/v1/analysis/clients)
# ---------------------------------------------------------------------------
@router.get(
    "/clients/bubble",
    summary="Get Client Bubble Network Graph Data & Itemized Transactions",
    description="Returns Client Bubble Network Graph dataset with embedded itemized transaction records per client node."
)
async def get_client_bubble_graph(
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await SpotliteEngine.compute_client_bubble_data(db, business_id=business_id)
        return success_response("Client bubble graph data fetched successfully", data=data)
    except Exception as e:
        return error_response(f"Failed to fetch client bubble graph data: {str(e)}", status_code=500)


@router.get(
    "/clients/analytics",
    summary="Get Client Directory & Revenue Matrix",
    description="Returns master client directory, revenue share matrix, DSO drift, and churn risk scanner."
)
async def get_client_analytics(
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await SpotliteEngine.compute_client_analytics(db, business_id=business_id)
        return success_response("Client analytics fetched successfully", data=data)
    except Exception as e:
        return error_response(f"Failed to fetch client analytics: {str(e)}", status_code=500)


@router.get(
    "/clients/bubble/{client_id}/transactions",
    summary="Get Itemized Transactions for Selected Client Node",
    description="Returns itemized transaction records for a specific client node selected from the bubble graph."
)
async def get_client_bubble_transactions(
    client_id: str,
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        bubble_data = await SpotliteEngine.compute_client_bubble_data(db, business_id=business_id)
        matching_client = next(
            (c for c in bubble_data["client_bubbles"] if c["client_id"].lower() == client_id.lower() or c["client_name"].lower() == client_id.lower()),
            None
        )
        if not matching_client:
            return error_response(f"Client node '{client_id}' not found", status_code=404)
        return success_response(f"Transactions for client '{matching_client['client_name']}' fetched successfully", data={
            "client_id": matching_client["client_id"],
            "client_name": matching_client["client_name"],
            "category": matching_client["category"],
            "annual_contract_value": matching_client["annual_contract_value"],
            "monthly_revenue": matching_client["monthly_revenue"],
            "status": matching_client["status"],
            "transaction_count": len(matching_client["transactions"]),
            "transactions": matching_client["transactions"]
        })
    except Exception as e:
        return error_response(f"Failed to fetch client transactions: {str(e)}", status_code=500)


# ---------------------------------------------------------------------------
# 5. Vendor Analytics & Bubble Network Graph Endpoints (/api/v1/analysis/vendors)
# ---------------------------------------------------------------------------
@router.get(
    "/vendors/bubble",
    summary="Get Vendor Bubble Network Graph Data & Itemized Transactions",
    description="Returns Vendor Bubble Network Graph dataset with embedded itemized transaction records for vendors and unmapped debits."
)
async def get_vendor_bubble_graph(
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await SpotliteEngine.compute_vendor_bubble_data(db, business_id=business_id)
        return success_response("Vendor bubble graph data fetched successfully", data=data)
    except Exception as e:
        return error_response(f"Failed to fetch vendor bubble graph data: {str(e)}", status_code=500)


@router.get(
    "/vendors/analytics",
    summary="Get Vendor Directory & Fixed/Variable Opex Matrix",
    description="Returns master vendor directory, fixed/variable debit classification, spend creep, and single-vendor dependency risks."
)
async def get_vendor_analytics(
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await SpotliteEngine.compute_vendor_analytics(db, business_id=business_id)
        return success_response("Vendor analytics fetched successfully", data=data)
    except Exception as e:
        return error_response(f"Failed to fetch vendor analytics: {str(e)}", status_code=500)


@router.get(
    "/vendors/bubble/{vendor_id}/transactions",
    summary="Get Itemized Transactions for Selected Vendor Node",
    description="Returns itemized transaction records for a specific vendor node or 'Others' node selected from the bubble graph."
)
async def get_vendor_bubble_transactions(
    vendor_id: str,
    business_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        bubble_data = await SpotliteEngine.compute_vendor_bubble_data(db, business_id=business_id)
        matching_vendor = next(
            (v for v in bubble_data["vendor_bubbles"] if v["vendor_id"].lower() == vendor_id.lower() or v["vendor_name"].lower() == vendor_id.lower()),
            None
        )
        if not matching_vendor:
            return error_response(f"Vendor node '{vendor_id}' not found", status_code=404)
        return success_response(f"Transactions for vendor '{matching_vendor['vendor_name']}' fetched successfully", data={
            "vendor_id": matching_vendor["vendor_id"],
            "vendor_name": matching_vendor["vendor_name"],
            "category": matching_vendor["category"],
            "cost_classification": matching_vendor["cost_classification"],
            "monthly_spend": matching_vendor["monthly_spend"],
            "status": matching_vendor["status"],
            "transaction_count": len(matching_vendor["transactions"]),
            "is_others": matching_vendor.get("is_others", False),
            "transactions": matching_vendor["transactions"]
        })
    except Exception as e:
        return error_response(f"Failed to fetch vendor transactions: {str(e)}", status_code=500)
