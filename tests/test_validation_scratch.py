import re
from typing import Any, Dict, List
from datetime import date
from decimal import Decimal

REQUIRED_FIELDS = [
    "client_id",
    "client_name",
    "category",
    "contract_value",
    "revenue",
    "frequency",
    "bank_name",
    "account_holder_name",
    "account_number",
    "ifsc_code",
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
REQUIRED_CLIENT_COLUMNS = {
    "client_id": "client_id",
    "client_name": "client_name",
    "legal_name": "legal_name",
    "category": "category",
    "industry": "industry",
    "contract_id": "contract_id",
    "contract_type": "contract_type",
    "contract_start_date": "contract_start_date",
    "contract_end_date": "contract_end_date",
    "contract_value": "contract_value",
    "currency": "currency",
    "revenue": "revenue",
    "payment_type": "payment_type",
    "frequency": "frequency",
    "recurring": "recurring",
    "bank_name": "bank_name",
    "account_holder_name": "account_holder_name",
    "account_number": "account_number",
    "ifsc_code": "ifsc_code",
    "status": "status",
}

def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    return s.lower().replace("_", " ").replace("-", " ")

def _normalize_row(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, val in record.items():
        canonical = None
        cleaned = _normalize_key(key)
        for canonical_key, variations in REQUIRED_CLIENT_COLUMNS.items():
            if cleaned == canonical_key.replace("_", " ") or cleaned == variations.replace("_", " "):
                canonical = canonical_key
                break
        if canonical is None:
            normalized[key] = val
            continue
            
        if canonical in {"account_number", "ifsc_code", "client_id", "client_name", "legal_name", "category", "industry", "contract_id", "contract_type", "currency", "payment_type", "frequency", "recurring", "bank_name", "account_holder_name", "status"}:
            if val is not None:
                normalized[canonical] = str(val)
            else:
                normalized[canonical] = None
        else:
            normalized[canonical] = val
    return normalized

class ClientValidationService:
    @staticmethod
    def _is_blank(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value).replace(",", "").replace("₹", "").replace("$", "").replace("INR", "").strip())
        except Exception:
            return None

    @staticmethod
    def validate_record(record: Dict[str, Any], is_upload: bool = False) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        for field in REQUIRED_FIELDS:
            value = record.get(field)
            if ClientValidationService._is_blank(value):
                errors.append({"row": record.get("sourceRow") or record.get("row"), "field": field, "error": f"{field.replace('_', ' ').title()} is required"})
                continue
            if field in {"contract_value", "revenue"}:
                if ClientValidationService._parse_decimal(value) is None:
                    errors.append({"row": record.get("sourceRow") or record.get("row"), "field": field, "error": f"{field.replace('_', ' ').title()} must be numeric"})

        for key in record.keys():
            if key not in REQUIRED_FIELDS and key not in OPTIONAL_FIELDS and key not in {"row", "sourceRow", "source_row"}:
                errors.append({"row": record.get("sourceRow") or record.get("row"), "field": key, "error": f"Unsupported Excel column"})
                
        if not ClientValidationService._is_blank(record.get("ifsc_code")):
            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(record.get("ifsc_code")).upper()):
                errors.append({"row": record.get("sourceRow") or record.get("row"), "field": "ifsc_code", "error": "IFSC code is invalid"})

        return {"valid": not errors, "errors": errors}

print("Test 1 (Unsupported column):", ClientValidationService.validate_record(_normalize_row({"CLIENT ID": "123", "contract_value": 100, "UnknownCol": "yes"})))
