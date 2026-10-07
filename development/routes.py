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
        from app.business.models import Cache
        from sqlalchemy import select
        from datetime import datetime, timedelta
        import uuid

        biz_uuid = None
        try:
            biz_uuid = uuid.UUID(company_id)
            cache_res = await db.execute(select(Cache).where(Cache.business_id == biz_uuid))
            cache = cache_res.scalar_one_or_none()
            if cache and cache.development_news and cache.updated_at > datetime.now() - timedelta(days=7):
                return cache.development_news
        except ValueError:
            cache = None

        service = DevelopmentService()
        data = await service.fetch_company_developments(
            company_id=company_id,
            db=db,
            limit=limit,
            days=days,
            category=category,
        )

        if biz_uuid:
            if cache:
                cache.development_news = data
                cache.updated_at = datetime.now()
            else:
                cache = Cache(
                    business_id=biz_uuid,
                    development_news=data,
                    updated_at=datetime.now()
                )
                db.add(cache)
            await db.commit()

        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development lookup failed due to an upstream issue.",
        ) from exc
