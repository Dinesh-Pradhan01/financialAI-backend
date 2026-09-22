import re
from typing import Dict, Any, List
from app.upload_engine.normalizers.base_normalizer import BaseNormalizer
import math

class ClientNormalizer(BaseNormalizer):
    def _apply_business_logic(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if record.get("client_id") is None:
            record["client_id"] = ""
        return record
