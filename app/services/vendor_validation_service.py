from typing import Dict, Any, List

REQUIRED_VENDOR_FIELDS = [
    "vendor_id",
    "vendor_name",
    "category",
    "contract_value",
    "cost",  # or monthly_cost
    "frequency",
    "bank_name",
    "account_holder_name",
    "account_number",
    "ifsc_code",
]

class VendorValidationResult:
    def __init__(self, ready_to_import: bool, missing_required_fields: List[str]):
        self.ready_to_import = ready_to_import
        self.missing_required_fields = missing_required_fields

class VendorValidationService:
    @staticmethod
    def validate_preview_row(record: Dict[str, Any]) -> VendorValidationResult:
        missing_fields = []
        for field in REQUIRED_VENDOR_FIELDS:
            if field == "cost":
                val = record.get("monthly_cost") if "monthly_cost" in record else record.get("cost")
            else:
                val = record.get(field)
            if val is None or str(val).strip() == "":
                missing_fields.append(field)
                
        return VendorValidationResult(
            ready_to_import=len(missing_fields) == 0,
            missing_required_fields=missing_fields
        )
