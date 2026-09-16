from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime


IGNORED_COMPARISON_FIELDS = {
    "created_at",
    "updated_at",
    "upload_id",
    "agreement_document_id",
    "agreement_file_name",
    "agreement_extraction_confidence",
    "id",
    "is_deleted",
}

BUSINESS_FIELDS = [
    "client_id",
    "client_name",
    "legal_name",
    "category",
    "industry",
    "contract_id",
    "contract_type",
    "contract_start_date",
    "contract_end_date",
    "contract_value",
    "currency",
    "revenue",
    "payment_type",
    "frequency",
    "recurring",
    "bank_name",
    "account_holder_name",
    "account_number",
    "ifsc_code",
    "status",
]


class ClientComparisonService:
    @staticmethod
    def business_key(record: Dict[str, Any]) -> Tuple[str, str]:
        return (str(record.get("client_id") or "").strip(), str(record.get("category") or "").strip())

    @staticmethod
    def _normalize_scalar(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "":
                return None
            return cleaned.lower() if cleaned.lower() not in {"none", "null", "nan", "n/a"} else None
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, date):
            return value.isoformat()
        return value

    @staticmethod
    def _decimal_value(value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        try:
            if isinstance(value, Decimal):
                return value
            val = str(value).replace(",", "").replace("₹", "").replace("$", "").replace("INR", "").strip()
            return Decimal(val)
        except Exception:
            return None

    @staticmethod
    def _normalize_for_compare(field: str, value: Any) -> Any:
        if value is None:
            return None
        if field in {"contract_value", "revenue"}:
            dec = ClientComparisonService._decimal_value(value)
            return float(dec) if dec is not None else None
        if field in {"contract_start_date", "contract_end_date"}:
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, str):
                try:
                    return date.fromisoformat(value[:10]).isoformat()
                except Exception:
                    return str(value).strip()
        return ClientComparisonService._normalize_scalar(value)

    @staticmethod
    def compare_record(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
        if existing is None:
            return {"action": "INSERT", "changed_fields": [], "existing_record": None}

        changed_fields: List[str] = []
        for field in BUSINESS_FIELDS:
            if field in IGNORED_COMPARISON_FIELDS:
                continue
            existing_val = ClientComparisonService._normalize_for_compare(field, existing.get(field))
            incoming_val = ClientComparisonService._normalize_for_compare(field, incoming.get(field))
            if existing_val != incoming_val:
                changed_fields.append(field)

        if not changed_fields:
            return {"action": "SKIP", "changed_fields": [], "existing_record": existing}
        return {"action": "UPDATE", "changed_fields": changed_fields, "existing_record": existing}

    @staticmethod
    def detect_conflict(input_value: Any, agreement_value: Any) -> Dict[str, Any]:
        input_number = input_value.get("contract_value") if isinstance(input_value, dict) else input_value
        agreement_number = agreement_value.get("contract_value") if isinstance(agreement_value, dict) else agreement_value

        if input_number is None or agreement_number is None:
            return {"field": "contract_value", "input_value": input_number, "agreement_value": agreement_number, "conflict": False}

        left = ClientComparisonService._decimal_value(input_number)
        right = ClientComparisonService._decimal_value(agreement_number)
        if left is None or right is None:
            return {"field": "contract_value", "input_value": input_number, "agreement_value": agreement_number, "conflict": False}
        if float(left) != float(right):
            return {"field": "contract_value", "input_value": float(left), "agreement_value": float(right), "conflict": True}
        return {"field": "contract_value", "input_value": float(left), "agreement_value": float(right), "conflict": False}
