import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.api.spotlite.service import SpotliteService
from app.api.spotlite.schemas import (
    SpotliteFullReport,
    ExecutiveScorecardItem,
    HeaderMetadataResponse,
    MacroCashFlowResponse,
    TemporalPatternsResponse,
    ChannelDistributionResponse,
    AnomalyRiskResponse,
    EfficiencyProjectionsResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Spotlite"])


@router.get(
    "/report",
    response_model=SpotliteFullReport,
    summary="Get Complete Spotlite Non-Entity Analytics Report",
    description="Calculates all non-entity statement & cash flow metrics at once and returns the complete analytics report."
)
async def get_full_spotlite_report(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report
    except Exception as e:
        logger.error(f"Error computing Spotlite report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate Spotlite report: {str(e)}")


@router.get(
    "/executive-summary",
    response_model=List[ExecutiveScorecardItem],
    summary="Executive Summary & Financial Scorecard",
    description="Returns the executive scorecard summarizing key indicators across liquidity, burn rate, runway, and anomaly controls."
)
async def get_executive_summary(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.executive_summary
    except Exception as e:
        logger.error(f"Error fetching executive summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch executive summary: {str(e)}")


@router.get(
    "/header-metadata",
    response_model=HeaderMetadataResponse,
    summary="Section 1: Statement & Account Header Metadata",
    description="Returns bank account header metadata extracted directly from native statement headers and database records."
)
async def get_header_metadata(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_1_header_metadata
    except Exception as e:
        logger.error(f"Error fetching header metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch header metadata: {str(e)}")


@router.get(
    "/macro-cash-flow",
    response_model=MacroCashFlowResponse,
    summary="Section 2: Macro Cash Flow & Liquidity Analysis",
    description="Returns monthly cash flow trajectory, outflow burn rates, cash runway, liquidity buffer, and idle cash reserves."
)
async def get_macro_cash_flow(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_2_macro_cash_flow
    except Exception as e:
        logger.error(f"Error fetching macro cash flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch macro cash flow: {str(e)}")


@router.get(
    "/temporal-patterns",
    response_model=TemporalPatternsResponse,
    summary="Section 3: Time-Based & Temporal Pattern Analysis",
    description="Returns day-of-month cash flow distributions, month-end liquidity dip metrics, and day-of-week spend cyclicality."
)
async def get_temporal_patterns(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_3_temporal_patterns
    except Exception as e:
        logger.error(f"Error fetching temporal patterns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch temporal patterns: {str(e)}")


@router.get(
    "/channel-distribution",
    response_model=ChannelDistributionResponse,
    summary="Section 4: Transaction Channel & Payment Method Distribution",
    description="Returns payment channel breakdown (RTGS, NEFT, UPI, POS/Card, Auto-Debit/ACH) with volume and outflow shares."
)
async def get_channel_distribution(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_4_channel_distribution
    except Exception as e:
        logger.error(f"Error fetching channel distribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch channel distribution: {str(e)}")


@router.get(
    "/anomalies-and-outliers",
    response_model=AnomalyRiskResponse,
    summary="Section 5: Pure Anomaly, Risk & Outlier Analysis",
    description="Returns statistical category outliers (Z-score > 2.0σ) and duplicate transaction flags. Note: Statement Arithmetic and Round-Number Anomalies have been removed."
)
async def get_anomalies_and_outliers(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_5_anomaly_risk
    except Exception as e:
        logger.error(f"Error fetching anomalies and outliers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch anomalies and outliers: {str(e)}")


@router.get(
    "/efficiency-and-projections",
    response_model=EfficiencyProjectionsResponse,
    summary="Section 6: Financial Efficiency & Projections",
    description="Returns operational efficiency ratios (cost-to-income, net margin proxy) and annualized run-rate projections."
)
async def get_efficiency_and_projections(
    company_name: Optional[str] = Query(None, description="Target company name"),
    business_id: Optional[str] = Query(None, description="Business profile UUID"),
    db: AsyncSession = Depends(get_db)
):
    try:
        report = await SpotliteService.compute_spotlite_report(db, company_name=company_name, business_id=business_id)
        return report.section_6_efficiency_projections
    except Exception as e:
        logger.error(f"Error fetching efficiency and projections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch efficiency and projections: {str(e)}")
