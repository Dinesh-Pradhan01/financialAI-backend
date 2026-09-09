from typing import List, Dict, Any

class PreviewBuilder:
    @staticmethod
    def build(upload_id: str, records: List[Dict[str, Any]], issues: List[Dict[str, Any]], module_name: str = "generic") -> Dict[str, Any]:
        error_row_ids = set()
        warning_row_ids = set()
        duplicate_ids = sum(1 for i in issues if i["code"] == "DUPLICATE_ERROR")
        missing_required = sum(1 for i in issues if i["code"] == "MISSING_FIELD")
        
        for issue in issues:
            if issue["severity"] == "error":
                error_row_ids.add(issue["rowId"])
            elif issue["severity"] == "warning":
                warning_row_ids.add(issue["rowId"])
                
        valid_records = 0
        for record in records:
            if not record.get("isBlank") and record.get("rowId") not in error_row_ids:
                valid_records += 1

        summary = {
            "validRecords": valid_records,
            "warnings": len([i for i in issues if i["severity"] == "warning"]),
            "errors": len([i for i in issues if i["severity"] == "error"]),
            "issues": issues,
            "errorRowIds": list(error_row_ids),
            "warningRowIds": list(warning_row_ids),
            "duplicateIds": duplicate_ids,
            "missingRequiredFields": missing_required
        }
        
        if module_name == "employee":
            summary["validEmployees"] = valid_records
        elif module_name == "vendor":
            summary["validVendors"] = valid_records
        
        return {
            "upload_id": str(upload_id),
            "records": records,
            "summary": summary
        }
