import logging
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models.vendor import VendorMaster
from app.services.agreement.normalization_service import NormalizationService

logger = logging.getLogger(__name__)

from app.services.vendor_validation_service import VendorValidationService, REQUIRED_VENDOR_FIELDS

BUSINESS_COMPARE_FIELDS = [
    "vendor_name",
    "legal_name",
    "industry",
    "contract_id",
    "contract_type",
    "contract_start_date",
    "contract_end_date",
    "contract_value",
    "currency",
    "monthly_cost",
    "payment_type",
    "frequency",
    "recurring",
    "bank_name",
    "account_holder_name",
    "account_number",
    "ifsc_code",
    "status",
]

def normalize_val(val: Any) -> Any:
    if val is None:
        return ""
    if isinstance(val, (int, float, Decimal)):
        try:
            return round(float(val), 4)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(val, str):
        s_val = val.strip()
        # If it's a numeric string, normalize to float float
        try:
            if s_val and (s_val.replace(".", "", 1).isdigit() or (s_val.startswith("-") and s_val[1:].replace(".", "", 1).isdigit())):
                return round(float(s_val), 4)
        except (ValueError, TypeError):
            pass
        return s_val
    if isinstance(val, date):
        return val.isoformat()
    return str(val).strip()

def is_field_changed(existing_val: Any, incoming_val: Any) -> bool:
    norm_exist = normalize_val(existing_val)
    norm_inc = normalize_val(incoming_val)
    if norm_exist == "" and norm_inc == "":
        return False
    return norm_exist != norm_inc

class VendorIngestionService:
    @staticmethod
    async def process_records(
        records: List[Dict[str, Any]],
        db: AsyncSession,
        imported_by: str = "system"
    ) -> Dict[str, Any]:
        total_records = len(records)
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        results = []

        if not records:
            return {
                "total_records": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "results": []
            }

        # 1. Fetch existing vendors from DB
        query = select(VendorMaster).where(VendorMaster.is_deleted == False)
        db_result = await db.execute(query)
        existing_vendors = db_result.scalars().all()

        # Map existing vendors by composite key (vendor_id.strip(), category.strip())
        db_map: Dict[Tuple[str, str], VendorMaster] = {
            (v.vendor_id.strip(), v.category.strip()): v for v in existing_vendors
        }

        # Track keys processed within the same batch to handle intra-batch updates/inserts
        batch_seen: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for idx, row in enumerate(records):
            # Clean row dictionary
            c_row = {k: v for k, v in row.items() if k not in ["rowId", "sourceRow", "isBlank"]}

            # Map 'cost' header variation to 'monthly_cost'
            if "cost" in c_row and ("monthly_cost" not in c_row or c_row["monthly_cost"] is None or str(c_row["monthly_cost"]).strip() == ""):
                c_row["monthly_cost"] = c_row["cost"]

            raw_vendor_id = c_row.get("vendor_id")
            raw_category = c_row.get("category")

            # Check missing required fields
            validation_result = VendorValidationService.validate_preview_row(c_row)
            missing_fields = validation_result.missing_required_fields

            if missing_fields:
                failed_count += 1
                results.append({
                    "vendor_id": str(raw_vendor_id) if raw_vendor_id else f"ROW_{idx+1}",
                    "category": str(raw_category) if raw_category else "UNKNOWN",
                    "action": "INVALID",
                    "status": "failed",
                    "reason": f"Missing required field(s): {', '.join(missing_fields)}"
                })
                continue

            vendor_id = str(raw_vendor_id).strip()
            category = str(raw_category).strip()
            key = (vendor_id, category)

            # Ensure numeric fields parsed
            try:
                contract_val = float(c_row.get("contract_value", 0))
                monthly_c = float(c_row.get("monthly_cost", 0))
            except (ValueError, TypeError):
                failed_count += 1
                results.append({
                    "vendor_id": vendor_id,
                    "category": category,
                    "action": "INVALID",
                    "status": "failed",
                    "reason": "Invalid numeric value for contract_value or monthly_cost"
                })
                continue

            # Build normalized record data dictionary
            rec_data = {
                "vendor_id": vendor_id,
                "vendor_name": str(c_row.get("vendor_name", "")).strip(),
                "category": category,
                "contract_id": str(c_row.get("contract_id", "")).strip() if c_row.get("contract_id") is not None else None,
                "contract_value": contract_val,
                "monthly_cost": monthly_c,
                "frequency": str(c_row.get("frequency", "")).strip(),
                "bank_name": str(c_row.get("bank_name", "")).strip(),
                "account_holder_name": str(c_row.get("account_holder_name", "")).strip(),
                "account_number": str(c_row.get("account_number", "")).strip(),
                "ifsc_code": str(c_row.get("ifsc_code", "")).strip(),
                "legal_name": str(c_row.get("legal_name", "")).strip() if c_row.get("legal_name") else None,
                "industry": str(c_row.get("industry", "")).strip() if c_row.get("industry") else None,
                "contract_type": str(c_row.get("contract_type", "")).strip() if c_row.get("contract_type") else None,
                "contract_start_date": NormalizationService._normalize_date(str(c_row.get("contract_start_date", ""))) if c_row.get("contract_start_date") else None,
                "contract_end_date": NormalizationService._normalize_date(str(c_row.get("contract_end_date", ""))) if c_row.get("contract_end_date") else None,
                "currency": str(c_row.get("currency", "")).strip() if c_row.get("currency") else None,
                "payment_type": str(c_row.get("payment_type", "")).strip() if c_row.get("payment_type") else None,
                "recurring": str(c_row.get("recurring", "")).strip() if c_row.get("recurring") else None,
                "status": str(c_row.get("status", "")).strip() if c_row.get("status") else None,
            }

            # Check if key exists in DB or was processed earlier in batch
            existing_db_obj = db_map.get(key)

            if existing_db_obj:
                # Compare business fields
                changed_fields = []
                for field in BUSINESS_COMPARE_FIELDS:
                    exist_v = getattr(existing_db_obj, field, None)
                    inc_v = rec_data.get(field)
                    if is_field_changed(exist_v, inc_v):
                        changed_fields.append(field)

                if not changed_fields:
                    # EXACT DUPLICATE -> SKIP
                    skipped_count += 1
                    results.append({
                        "vendor_id": vendor_id,
                        "category": category,
                        "action": "SKIPPED",
                        "status": "duplicate",
                        "reason": "Already present with no changes"
                    })
                else:
                    # CHANGED DATA -> UPDATE
                    updated_count += 1
                    for field in changed_fields:
                        setattr(existing_db_obj, field, rec_data[field])
                    existing_db_obj.updated_at = datetime.now(timezone.utc)
                    existing_db_obj.updated_by = imported_by

                    results.append({
                        "vendor_id": vendor_id,
                        "category": category,
                        "action": "UPDATED",
                        "status": "updated",
                        "reason": "Existing vendor data changed",
                        "changed_fields": changed_fields
                    })
            elif key in batch_seen:
                # Intra-batch duplicate check
                prev_data = batch_seen[key]
                changed_fields = [f for f in BUSINESS_COMPARE_FIELDS if is_field_changed(prev_data.get(f), rec_data.get(f))]
                if not changed_fields:
                    skipped_count += 1
                    results.append({
                        "vendor_id": vendor_id,
                        "category": category,
                        "action": "SKIPPED",
                        "status": "duplicate",
                        "reason": "Already present with no changes (duplicate in file)"
                    })
                else:
                    skipped_count += 1
                    results.append({
                        "vendor_id": vendor_id,
                        "category": category,
                        "action": "SKIPPED",
                        "status": "duplicate",
                        "reason": "Duplicate key in file"
                    })
            else:
                # NEW VENDOR -> INSERT
                inserted_count += 1
                new_vendor = VendorMaster(
                    **rec_data,
                    created_by=imported_by,
                    updated_by=imported_by,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_vendor)
                db_map[key] = new_vendor
                batch_seen[key] = rec_data

                results.append({
                    "vendor_id": vendor_id,
                    "category": category,
                    "action": "INSERTED",
                    "status": "inserted",
                    "reason": "New Vendor ID + Category combination"
                })

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Error committing vendor ingestion: {e}")
            raise e

        return {
            "total_records": total_records,
            "inserted": inserted_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "results": results
        }
