import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.repositories.vendor import vendor_repository
from app.db.models.vendor import VendorMaster
from app.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse

def parse_float(val) -> float:
    try:
        if val is None or str(val).strip() == "":
            return 0.0
        return float(val)
    except ValueError:
        return 0.0

def calculate_expected_billing(data: VendorCreate) -> float:
    base = parse_float(data.base_cost)
    support = parse_float(data.support_cost)
    maint = parse_float(data.maintenance_cost)
    hosting = parse_float(data.hosting_cost)
    cloud = parse_float(data.cloud_cost)
    misc = parse_float(data.miscellaneous_cost)
    
    subtotal = base + support + maint + hosting + cloud + misc
    tax_percent = parse_float(data.tax_percentage)
    tax_amount = subtotal * (tax_percent / 100.0)
    discount = parse_float(data.discount)
    
    return subtotal + tax_amount - discount

async def get_vendors(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    industry: Optional[str] = None,
    status: Optional[str] = None,
    recurring: Optional[bool] = None,
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
            VendorMaster.contract_id.ilike(f"%{search}%"),
            VendorMaster.gst_number.ilike(f"%{search}%"),
            VendorMaster.pan_number.ilike(f"%{search}%"),
            VendorMaster.project_name.ilike(f"%{search}%")
        )
        filters.append(search_filter)
        
    if industry:
        filters.append(VendorMaster.industry == industry)
    if status:
        filters.append(VendorMaster.status == status)
    if recurring is not None:
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
    calc_val = calculate_expected_billing(vendor_in)
    vendor_in.expected_billing = round(calc_val, 2)
    
    return await vendor_repository.create(db, obj_in=vendor_in)

async def update_vendor(
    db: AsyncSession, *, db_obj: VendorMaster, obj_in: VendorUpdate
) -> VendorMaster:
    # Recalculate if costs changed
    update_data = obj_in.model_dump(exclude_unset=True)
    cost_fields = ['base_cost', 'support_cost', 'maintenance_cost', 'hosting_cost', 'cloud_cost', 'miscellaneous_cost', 'tax_percentage', 'discount']
    
    if any(field in update_data for field in cost_fields):
        temp_create = VendorCreate(**{**db_obj.__dict__, **update_data})
        calc_val = calculate_expected_billing(temp_create)
        obj_in.expected_billing = round(calc_val, 2)
        
    return await vendor_repository.update(db, db_obj=db_obj, obj_in=obj_in)

async def delete_vendor(db: AsyncSession, id: uuid.UUID) -> VendorMaster:
    return await vendor_repository.remove(db, id=id)
