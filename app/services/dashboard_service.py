from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict

from app.db.models.employee import EmployeeMaster
from app.db.models.vendor import VendorMaster
from app.db.models.upload import ImportLogs, UploadHistory

async def get_employee_dashboard_metrics(db: AsyncSession):
    # Fetch all employees to avoid casting issues in SQLite/Postgres since numbers are stored as string
    query = select(EmployeeMaster).where(EmployeeMaster.is_deleted == False)
    result = await db.execute(query)
    employees = result.scalars().all()

    total_employees = len(employees)
    active_employees = 0
    inactive_employees = 0
    departments = defaultdict(int)
    
    total_salary = 0
    highest_salary = 0
    salary_count = 0

    for emp in employees:
        # Status
        status = (emp.status or "").lower()
        if status == "active":
            active_employees += 1
        elif status in ["inactive", "terminated", "resigned"]:
            inactive_employees += 1
            
        # Department
        if emp.department:
            departments[emp.department] += 1
            
        # Salary
        if emp.salary:
            try:
                # Remove commas or currency symbols if any
                clean_salary = "".join(c for c in emp.salary if c.isdigit() or c == '.')
                if clean_salary:
                    sal = float(clean_salary)
                    total_salary += sal
                    highest_salary = max(highest_salary, sal)
                    salary_count += 1
            except ValueError:
                pass

    avg_salary = total_salary / salary_count if salary_count > 0 else 0

    return {
        "totalEmployees": total_employees,
        "activeEmployees": active_employees,
        "inactiveEmployees": inactive_employees,
        "averageSalary": avg_salary,
        "highestSalary": highest_salary,
        "departments": dict(departments)
    }

async def get_vendor_dashboard_metrics(db: AsyncSession):
    query = select(VendorMaster).where(VendorMaster.is_deleted == False)
    result = await db.execute(query)
    vendors = result.scalars().all()

    total_vendors = len(vendors)
    recurring_vendors = 0
    industries = defaultdict(int)
    
    expected_billing = 0
    contract_value = 0
    revenue = 0

    for vendor in vendors:
        # Recurring
        if vendor.recurring:
            recurring_vendors += 1
            
        # Industry
        if vendor.industry:
            industries[vendor.industry] += 1
            
        def parse_currency(val):
            if not val:
                return 0
            clean_val = "".join(c for c in val if c.isdigit() or c == '.')
            try:
                return float(clean_val) if clean_val else 0
            except ValueError:
                return 0

        eb = float(vendor.expected_billing or 0)
        cv = float(vendor.contract_value or 0)
        
        expected_billing += eb
        contract_value += cv
        revenue += eb # Mocking revenue as expected_billing for now

    return {
        "totalVendors": total_vendors,
        "recurringVendors": recurring_vendors,
        "expectedBilling": expected_billing,
        "contractValue": contract_value,
        "revenue": revenue,
        "industries": dict(industries)
    }

async def get_recent_activity(db: AsyncSession, limit: int = 5):
    # Fetch recent upload history logs regardless of status
    query = select(UploadHistory).order_by(UploadHistory.created_at.desc()).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    activities = []
    for log in logs:
        activities.append({
            "upload_id": str(log.id),
            "upload_type": log.upload_type,
            "file_name": log.file_name,
            "uploaded_at": log.created_at.isoformat() if log.created_at else None,
            "record_count": log.total_records or 0,
            "status": log.status
        })
        
    return activities

async def get_upload_preview(db: AsyncSession, upload_id: str):
    # Fetch import logs to find the entity_ids associated with this upload
    query = select(ImportLogs).where(ImportLogs.upload_history_id == upload_id)
    result = await db.execute(query)
    import_logs = result.scalars().all()

    if not import_logs:
        return {"upload_type": None, "records": []}

    # All logs for an upload should be of the same entity_type
    entity_type = import_logs[0].entity_type
    entity_ids = [log.entity_id for log in import_logs if log.entity_id and log.entity_id != "ALL"]
    
    if not entity_ids:
        return {"upload_type": entity_type, "records": []}

    if entity_type == "EMPLOYEE":
        rec_query = select(EmployeeMaster).where(EmployeeMaster.employee_id.in_(entity_ids))
        rec_result = await db.execute(rec_query)
        records = rec_result.scalars().all()
        return {"upload_type": "Employee", "records": [r.__dict__ for r in records]}
    elif entity_type == "VENDOR":
        rec_query = select(VendorMaster).where(VendorMaster.vendor_id.in_(entity_ids))
        rec_result = await db.execute(rec_query)
        records = rec_result.scalars().all()
        return {"upload_type": "Vendor", "records": [r.__dict__ for r in records]}
    else:
        return {"upload_type": entity_type, "records": []}
