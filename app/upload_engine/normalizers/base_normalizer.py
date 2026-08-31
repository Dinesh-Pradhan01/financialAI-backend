import uuid
from typing import Dict, Any, List

class BaseNormalizer:
    def normalize(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for idx, record in enumerate(records):
            is_blank = all(v is None or str(v).strip() == "" for v in record.values())
            
            norm_rec = {
                "rowId": str(uuid.uuid4()),
                "sourceRow": idx + 1,
                "isBlank": is_blank
            }
            norm_rec.update(record)
            
            # Module specific processing
            norm_rec = self._apply_business_logic(norm_rec)
            normalized.append(norm_rec)
            
        return normalized
        
    def _apply_business_logic(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return record
