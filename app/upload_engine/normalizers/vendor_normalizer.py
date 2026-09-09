from typing import Dict, Any
from app.upload_engine.normalizers.base_normalizer import BaseNormalizer

def parse_float(val) -> float:
    try:
        if val is None or str(val).strip() == "":
            return 0.0
        return float(val)
    except ValueError:
        return 0.0

class VendorNormalizer(BaseNormalizer):
    def _apply_business_logic(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if record.get("vendor_id") is None:
            record["vendor_id"] = ""
        return record
