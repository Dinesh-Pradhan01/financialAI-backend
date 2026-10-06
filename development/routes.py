from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from development.service import DevelopmentService

router = APIRouter(tags=["Developments"])


@router.get("/{company_id}")
async def get_company_developments(
    company_id: str,
    limit: int = Query(10, ge=1, le=20),
    days: int = Query(15, ge=1, le=30),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = DevelopmentService()
        return await service.fetch_company_developments(
            company_id=company_id,
            db=db,
            limit=limit,
            days=days,
            category=category,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development lookup failed due to an upstream issue.",
        ) from exc
