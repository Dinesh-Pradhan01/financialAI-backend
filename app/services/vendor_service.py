from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.db.models.vendor import VendorMaster
from app.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse

async def get_vendors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    recurring: Optional[str] = None,
    currency: Optional[str] = None,
    contract_type: Optional[str] = None,
    payment_type: Optional[str] = None
) -> Dict[str, Any]:
    
    query = select(VendorMaster).where(VendorMaster.is_deleted == False)
    
    filters = []
    if search:
        search_filter = or_(
            VendorMaster.vendor_name.ilike(f"%{search}%"),
            VendorMaster.vendor_id.ilike(f"%{search}%"),
            VendorMaster.contract_id.ilike(f"%{search}%")
        )
        filters.append(search_filter)
        
    if industry:
        filters.append(VendorMaster.industry == industry)
    if status:
        filters.append(VendorMaster.status == status)
    if recurring:
        filters.append(VendorMaster.recurring == recurring)
    if currency:
        filters.append(VendorMaster.currency == currency)
    if contract_type:
        filters.append(VendorMaster.contract_type == contract_type)
    if payment_type:
        filters.append(VendorMaster.payment_type == payment_type)
        
    if filters:
        query = query.where(and_(*filters))
        
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    query = query.order_by(VendorMaster.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return {
        "items": [VendorResponse.model_validate(item).model_dump(mode="json") for item in items],
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit
    }

async def get_vendor_by_key(db: AsyncSession, vendor_id: str, category: Optional[str] = None) -> Optional[VendorMaster]:
    stmt = select(VendorMaster).where(
        and_(
            VendorMaster.vendor_id == vendor_id.strip(),
            VendorMaster.is_deleted == False
        )
    )
    if category:
        stmt = stmt.where(VendorMaster.category == category.strip())
    res = await db.execute(stmt)
    return res.scalars().first()

async def get_vendor_by_id(db: AsyncSession, id_val: Any, category: Optional[str] = None) -> Optional[VendorMaster]:
    return await get_vendor_by_key(db, str(id_val), category)

async def delete_vendor(db: AsyncSession, vendor_id: str, category: Optional[str] = None) -> bool:
    vendor = await get_vendor_by_key(db, vendor_id, category)
    if not vendor:
        return False
    vendor.is_deleted = True
    await db.commit()
    return True
