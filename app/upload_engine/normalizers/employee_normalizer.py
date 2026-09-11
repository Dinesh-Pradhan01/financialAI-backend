from typing import Dict, Any
from app.upload_engine.normalizers.base_normalizer import BaseNormalizer

class EmployeeNormalizer(BaseNormalizer):
    def _apply_business_logic(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if record.get("employee_id") is None and record.get("emp_id") is not None:
            record["employee_id"] = record["emp_id"]
        if record.get("emp_id") is None and record.get("employee_id") is not None:
            record["emp_id"] = record["employee_id"]
        if record.get("employee_id") is None:
            record["employee_id"] = ""
        return record
