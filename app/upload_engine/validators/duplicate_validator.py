from typing import Dict, Any, List
from app.upload_engine.validators.row_validator import _create_issue

class DuplicateValidator:
    @staticmethod
    def validate_duplicates(records: List[Dict[str, Any]], schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        unique_fields = [f["name"] for f in schema["fields"] if f.get("unique", False)]
        
        issues = []
        seen = {field: set() for field in unique_fields}
        
        for record in records:
            if record.get("isBlank"):
                continue
                
            for field in unique_fields:
                val = record.get(field)
                if val is not None and str(val).strip() != "":
                    if val in seen[field]:
                        issues.append(_create_issue(
                            record.get("rowId"), 
                            record.get("sourceRow"), 
                            field, 
                            f"Duplicate {field} found in batch: {val}", 
                            "DUPLICATE_ERROR"
                        ))
                    seen[field].add(val)
                    
        return issues
