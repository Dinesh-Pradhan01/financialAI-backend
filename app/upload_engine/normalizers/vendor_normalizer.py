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
            
        if not record.get("isBlank"):
            base = parse_float(record.get("base_cost"))
            support = parse_float(record.get("support_cost"))
            maint = parse_float(record.get("maintenance_cost"))
            hosting = parse_float(record.get("hosting_cost"))
            cloud = parse_float(record.get("cloud_cost"))
            misc = parse_float(record.get("miscellaneous_cost"))
            
            subtotal = base + support + maint + hosting + cloud + misc
            
            tax_percent = parse_float(record.get("tax_percentage"))
            tax_amount = subtotal * (tax_percent / 100.0)
            
            discount = parse_float(record.get("discount"))
            
            expected_billing = subtotal + tax_amount - discount
            record["expected_billing"] = round(expected_billing, 2)
            
        return record
