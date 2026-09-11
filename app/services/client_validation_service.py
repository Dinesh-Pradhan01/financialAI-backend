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
    def validate_record(record: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[Dict[str, Any]] = []
        for field in REQUIRED_FIELDS:
            value = record.get(field)
            if ClientValidationService._is_blank(value):
                errors.append({"row": record.get("sourceRow") or record.get("row"), "field": field, "error": f"{field.replace('_', ' ').title()} is required"})
                continue
            if field in {"contract_value", "revenue"}:
                if ClientValidationService._parse_decimal(value) is None:
                    errors.append({"row": record.get("sourceRow") or record.get("row"), "field": field, "error": f"{field.replace('_', ' ').title()} must be numeric"})

        if not ClientValidationService._is_blank(record.get("ifsc_code")):
            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(record.get("ifsc_code")).upper()):
                errors.append({"row": record.get("sourceRow") or record.get("row"), "field": "ifsc_code", "error": "IFSC code is invalid"})

        start_date = record.get("contract_start_date")
        end_date = record.get("contract_end_date")
        if start_date and end_date:
            try:
                if isinstance(start_date, str):
                    parsed_start = date.fromisoformat(start_date[:10])
                else:
                    parsed_start = start_date
                if isinstance(end_date, str):
                    parsed_end = date.fromisoformat(end_date[:10])
                else:
                    parsed_end = end_date
                if parsed_end < parsed_start:
                    errors.append({"row": record.get("sourceRow") or record.get("row"), "field": "contract_end_date", "error": "Contract end date cannot be before contract start date"})
            except Exception:
                pass

        return {"valid": not errors, "errors": errors}
