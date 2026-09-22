import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List


REQUIRED_FIELDS = [
    "client_id",
    "client_name",
    "category",
    "contract_value",
    "revenue",
    "frequency",
]
OPTIONAL_FIELDS = [
    "legal_name",
    "industry",
    "contract_id",
    "contract_type",
    "contract_start_date",
    "contract_end_date",
    "currency",
    "payment_type",
    "recurring",
    "status",
]


class ClientValidationResult:
    def __init__(self, ready_to_import: bool, missing_required_fields: List[str]):
        self.ready_to_import = ready_to_import
        self.missing_required_fields = missing_required_fields

class ClientValidationService:
    @staticmethod
    def validate_preview_row(record: Dict[str, Any]) -> ClientValidationResult:
        missing_fields = []
        for field in REQUIRED_FIELDS:
            if field == "revenue":
                val = record.get("revenue")
                if val is None or str(val).strip() == "":
                    c_type = str(record.get("contract_type") or record.get("contractType") or "").lower()
                    c_val = record.get("contract_value") or record.get("contractValue")
                    is_sub = "sub" in c_type or str(record.get("recurring", "")).lower() in ["true", "yes", "1"]
                    if is_sub and c_val:
                        try:
                            val = round(float(c_val) / 12.0, 2)
                            record["revenue"] = val
                        except (ValueError, TypeError):
                            pass
            else:
                val = record.get(field)
                if val is None and "_" in field:
                    parts = field.split("_")
                    camel = parts[0] + "".join(p.title() for p in parts[1:])
                    val = record.get(camel)
            if val is None or str(val).strip() == "":
                missing_fields.append(field)
                
        return ClientValidationResult(
            ready_to_import=len(missing_fields) == 0,
            missing_required_fields=missing_fields
        )
