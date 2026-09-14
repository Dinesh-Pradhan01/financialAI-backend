import re
import uuid
from typing import Dict, Any, List

def _create_issue(record_id: str, source_row: int, field: str, message: str, code: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "severity": "error",
        "code": code,
        "message": message,
        "rowId": record_id,
        "sourceRow": source_row,
        "field": field
    }

class RowValidator:
    @staticmethod
    def validate_row(record: Dict[str, Any], schema: Dict[str, Any], record_id: str, source_row: int) -> List[Dict[str, Any]]:
        issues = []
        for field in schema["fields"]:
            fname = field["name"]
            val = record.get(fname)
            if val is None and "_" in fname:
                parts = fname.split("_")
                camel = parts[0] + "".join(p.title() for p in parts[1:])
                val = record.get(camel)
            if val is None and fname == "monthly_cost":
                val = record.get("cost")

            if (val is None or str(val).strip() == "") and fname == "monthly_cost":
                c_type = str(record.get("contract_type") or record.get("contractType") or "").lower()
                c_val = record.get("contract_value") or record.get("contractValue")
                is_sub = "sub" in c_type or str(record.get("recurring", "")).lower() in ["true", "yes", "1"]
                if is_sub and c_val:
                    try:
                        val = round(float(c_val) / 12.0, 2)
                        record["monthly_cost"] = val
                        record["monthlyCost"] = val
                    except (ValueError, TypeError):
                        pass

            val_str = str(val).strip() if val is not None and str(val).strip() != "" else None
            
            # Required
            if field.get("required") and val_str is None:
                issues.append(_create_issue(record_id, source_row, fname, f"{fname.replace('_', ' ').title()} is required", "MISSING_FIELD"))
                continue
                
            if val_str is None:
                continue
                
            # Type checks
            ftype = field.get("type", "string")
            if ftype == "number":
                try:
                    num_val = float(val_str)
                    if "min" in field and num_val < field["min"]:
                        issues.append(_create_issue(record_id, source_row, fname, f"{fname} cannot be less than {field['min']}", "MIN_VALUE"))
                    if "max" in field and num_val > field["max"]:
                        issues.append(_create_issue(record_id, source_row, fname, f"{fname} cannot be greater than {field['max']}", "MAX_VALUE"))
                except ValueError:
                    issues.append(_create_issue(record_id, source_row, fname, f"{fname} must be a valid number", "INVALID_NUMBER"))
                    
            elif ftype == "email":
                if not re.match(r"[^@]+@[^@]+\.[^@]+", val_str):
                    issues.append(_create_issue(record_id, source_row, fname, f"Invalid email format", "INVALID_EMAIL"))
                    
            # Regex
            if "regex" in field:
                if not re.match(field["regex"], val_str):
                    issues.append(_create_issue(record_id, source_row, fname, f"Invalid format for {fname}", "FORMAT_ERROR"))
                    
            # Allowed Values
            if "allowed_values" in field:
                if val_str.lower() not in [x.lower() for x in field["allowed_values"]]:
                    issues.append(_create_issue(record_id, source_row, fname, f"Must be one of {field['allowed_values']}", "INVALID_VALUE"))
                    
            # Min Length
            if "min_length" in field:
                if len(val_str) < field["min_length"]:
                    issues.append(_create_issue(record_id, source_row, fname, f"Must be at least {field['min_length']} characters", "MIN_LENGTH"))
                    
            # Match Field
            if "match_field" in field:
                match_val = record.get(field["match_field"])
                match_val_str = str(match_val).strip() if match_val is not None else None
                if val_str != match_val_str:
                    issues.append(_create_issue(record_id, source_row, fname, f"Must match {field['match_field']}", "FIELD_MISMATCH"))

        return issues
