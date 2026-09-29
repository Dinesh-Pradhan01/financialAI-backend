"""
Spending API Routes (DEPRECATED & REMOVED)
------------------------------------------
The /api/v1/spending endpoints have been removed.
All analysis endpoints (overview, income, expenditure, clients, vendors) are available under /api/v1/analysis.
"""

from fastapi import APIRouter

router = APIRouter(prefix="", tags=["Spending"])
