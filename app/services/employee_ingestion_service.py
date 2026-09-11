import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.employee import EmployeeMaster, EmployeeVersion

BUSINESS_FIELDS = [
    "employee_name",
    "email",
    "joining_date",
    "department",
    "designation",
    "salary",
    "account_number",
    "ifsc_code",
    "bank_name",
    "employment_type",
    "status",
    "salary_frequency",
    "account_holder_name",
    "payment_mode",
]

REQUIRED_FIELDS = [
    "employee_id",
    "employee_name",
    "email",
    "joining_date",
    "department",
    "designation",
    "salary",
    "account_number",
    "ifsc_code",
    "bank_name",
]

def _normalize_val(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s != "" and s.lower() not in ("nan", "<na>", "none", "null") else None

def _validate_record(rec: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    emp_id = _normalize_val(rec.get("employee_id") or rec.get("emp_id"))
    if not emp_id:
        return False, "employee_id (or emp_id) is required"

    for field in REQUIRED_FIELDS:
        if field == "employee_id":
            continue
        v = _normalize_val(rec.get(field))
        if v is None:
            field_label = field.replace("_", " ").title()
            return False, f"{field_label} is required"

    # Validate email format
    email = _normalize_val(rec.get("email"))
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False, "Invalid email format"

    # Validate IFSC format
    ifsc = _normalize_val(rec.get("ifsc_code"))
    if ifsc and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc):
        return False, "Invalid IFSC code format"

    return True, None

class EmployeeIngestionService:
    @staticmethod
    async def process_ingestion(
        records: List[Dict[str, Any]], 
        db: AsyncSession, 
        imported_by: str = "system"
    ) -> Dict[str, Any]:
        
        inserted_count = 0
        updated_count = 0
        duplicate_count = 0
        failed_count = 0
        results: List[Dict[str, Any]] = []

        seen_batch_emp_ids = set()

        for rec in records:
            # Skip blank rows if marked
            if rec.get("isBlank"):
                continue

            emp_id = _normalize_val(rec.get("employee_id") or rec.get("emp_id"))
            if not emp_id:
                failed_count += 1
                results.append({
                    "emp_id": "UNKNOWN",
                    "status": "failed",
                    "message": "employee_id is required"
                })
                continue

            # Step 1 — Validate
            is_valid, err_msg = _validate_record(rec)
            if not is_valid:
                failed_count += 1
                results.append({
                    "emp_id": emp_id,
                    "status": "failed",
                    "message": err_msg
                })
                continue

            # Step 2 — Intra-batch duplicate check
            if emp_id in seen_batch_emp_ids:
                failed_count += 1
                results.append({
                    "emp_id": emp_id,
                    "status": "failed",
                    "message": f"Duplicate employee ID '{emp_id}' inside the same upload batch."
                })
                continue
            seen_batch_emp_ids.add(emp_id)

            # Step 3 — Query DB by emp_id (including soft-deleted records)
            stmt = select(EmployeeMaster).where(EmployeeMaster.employee_id == emp_id)
            res = await db.execute(stmt)
            existing_emp = res.scalars().first()

            # Cleaned business data dict for this record
            rec_business_data = {
                field: _normalize_val(rec.get(field))
                for field in BUSINESS_FIELDS
            }

            if existing_emp is None:
                # Case A — New Employee -> INSERT
                new_emp = EmployeeMaster(
                    employee_id=emp_id,
                    version=1,
                    created_by=imported_by,
                    updated_by=imported_by,
                    **rec_business_data
                )
                db.add(new_emp)

                # Create version 1 in employee_versions
                new_version = EmployeeVersion(
                    emp_id=emp_id,
                    version=1,
                    change_type="INITIAL",
                    created_by=imported_by,
                    **rec_business_data
                )
                db.add(new_version)

                inserted_count += 1
                results.append({
                    "emp_id": emp_id,
                    "status": "inserted",
                    "version": 1
                })
            elif existing_emp.is_deleted:
                # Case A2 — Previously Soft-deleted Employee -> Reactivate & Reset to Version 1
                existing_emp.is_deleted = False
                existing_emp.version = 1
                existing_emp.updated_by = imported_by
                existing_emp.updated_at = datetime.now(timezone.utc)
                for field in BUSINESS_FIELDS:
                    setattr(existing_emp, field, rec_business_data[field])
                db.add(existing_emp)

                new_version = EmployeeVersion(
                    emp_id=emp_id,
                    version=1,
                    change_type="INITIAL",
                    created_by=imported_by,
                    **rec_business_data
                )
                db.add(new_version)

                inserted_count += 1
                results.append({
                    "emp_id": emp_id,
                    "status": "inserted",
                    "version": 1
                })
            else:
                # Case B — Existing Employee -> Compare business fields
                changed_fields = []
                for field in BUSINESS_FIELDS:
                    old_val = _normalize_val(getattr(existing_emp, field, None))
                    new_val = rec_business_data[field]
                    if old_val != new_val:
                        changed_fields.append(field)

                if not changed_fields:
                    # Sub-case B1 — Exact Duplicate
                    duplicate_count += 1
                    results.append({
                        "emp_id": emp_id,
                        "status": "duplicate",
                        "message": f"Employee {emp_id} already exists with identical data."
                    })
                else:
                    # Sub-case B2 — Business Fields Changed -> UPDATE & BUMP VERSION
                    next_version = existing_emp.version + 1
                    existing_emp.version = next_version
                    existing_emp.updated_by = imported_by
                    existing_emp.updated_at = datetime.now(timezone.utc)
                    for field in BUSINESS_FIELDS:
                        setattr(existing_emp, field, rec_business_data[field])

                    db.add(existing_emp)

                    # Create new version in employee_versions
                    version_hist = EmployeeVersion(
                        emp_id=emp_id,
                        version=next_version,
                        change_type="UPDATED",
                        changed_fields=json.dumps(changed_fields),
                        created_by=imported_by,
                        **rec_business_data
                    )
                    db.add(version_hist)

                    updated_count += 1
                    results.append({
                        "emp_id": emp_id,
                        "status": "updated",
                        "version": next_version,
                        "changed_fields": changed_fields
                    })

        await db.commit()

        return {
            "total_records": len(results),
            "inserted": inserted_count,
            "updated": updated_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "results": results
        }
