import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.repositories.vendor import vendor_repository
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

async def get_vendor_by_id(db: AsyncSession, id: uuid.UUID) -> Optional[VendorMaster]:
    return await vendor_repository.get(db, id)

async def create_vendor(db: AsyncSession, vendor_in: VendorCreate) -> VendorMaster:
    return await vendor_repository.create(db, obj_in=vendor_in)

async def update_vendor(
    db: AsyncSession, *, db_obj: VendorMaster, obj_in: VendorUpdate
) -> VendorMaster:
    return await vendor_repository.update(db, db_obj=db_obj, obj_in=obj_in)

async def delete_vendor(db: AsyncSession, id: uuid.UUID) -> VendorMaster:
    return await vendor_repository.remove(db, id=id)
