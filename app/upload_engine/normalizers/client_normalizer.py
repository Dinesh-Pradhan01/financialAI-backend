import re
from typing import Dict, Any, List
from app.upload_engine.normalizers.base_normalizer import BaseNormalizer
import math

class ClientNormalizer(BaseNormalizer):
    def _apply_business_logic(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if record.get("client_id") is None:
            record["client_id"] = ""
        return record
    def normalize(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_records = []
        
        # In upload_engine, raw_records might contain unknown columns. 
        # BaseNormalizer maps keys based on the generic logic (lower, replace _, etc.)
        # But we want to replicate our new robust _normalize_key regex for camelCase handling.
        for idx, record in enumerate(records, start=2):
            normalized = {}
            # Preserve the sourceRow if already present, else use index
            normalized["sourceRow"] = record.get("sourceRow", idx)
            normalized["rowId"] = record.get("rowId", f"row-{normalized['sourceRow']}")
            
            # Check if it's completely blank
            is_blank = True
            
            for k, v in record.items():
                if k in ["sourceRow", "rowId", "isBlank"]:
                    continue
                    
                if v is not None and str(v).strip() != "" and not (isinstance(v, float) and math.isnan(v)):
                    is_blank = False
                    
                # Clean key using our fixed logic
                cleaned_key = self._normalize_key(k)
                canonical = None
                from app.api.cfo.clients.routes import REQUIRED_CLIENT_COLUMNS
                for canonical_key, variations in REQUIRED_CLIENT_COLUMNS.items():
                    if cleaned_key == canonical_key.replace("_", " ") or cleaned_key == variations.replace("_", " "):
                        canonical = canonical_key
                        break
                
                if canonical is None:
                    normalized[k] = None if isinstance(v, float) and math.isnan(v) else v
                    continue
                
                if canonical in {"account_number", "ifsc_code", "client_id", "client_name", "legal_name", "category", "industry", "contract_id", "contract_type", "currency", "payment_type", "frequency", "recurring", "bank_name", "account_holder_name", "status"}:
                    if v is not None and str(v).strip() != "" and not (isinstance(v, float) and math.isnan(v)):
                        normalized[canonical] = str(v).strip()
                    else:
                        normalized[canonical] = None
                else:
                    normalized[canonical] = None if isinstance(v, float) and math.isnan(v) else v
                    
            normalized["isBlank"] = is_blank
            normalized_records.append(normalized)
            
        return normalized_records

    def _normalize_key(self, value: Any) -> str:
        if value is None:
            return ""
        s = str(value).strip()
        # Insert space before capital letters to handle camelCase safely
        s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
        return s.lower().replace("_", " ").replace("-", " ")
