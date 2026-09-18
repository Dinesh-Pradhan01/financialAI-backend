import re
from typing import Any, Dict

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
    s = re.sub(r'(?<!^)(?=[A-Z])', ' ', s)
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
            continue
        normalized[canonical] = val
    return normalized

print("Test CLIENT ID:", _normalize_row({"CLIENT ID": "123"}))
print("Test client_id:", _normalize_row({"client_id": "123"}))
print("Test CLIENT_ID:", _normalize_row({"CLIENT_ID": "123"}))
