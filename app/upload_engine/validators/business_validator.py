from datetime import datetime
from typing import Dict, Any, List
from app.upload_engine.validators.row_validator import _create_issue

class BusinessValidator:
    @staticmethod
    def validate(module_name: str, record: Dict[str, Any], schema: Dict[str, Any], record_id: str, source_row: int) -> List[Dict[str, Any]]:
        issues = []
        
        # Dispatch to module specific rules
        if module_name == "employee":
            issues.extend(BusinessValidator._validate_employee(record, record_id, source_row))
        elif module_name == "vendor":
            issues.extend(BusinessValidator._validate_vendor(record, record_id, source_row))
        elif module_name == "client":
            issues.extend(BusinessValidator._validate_client(record, record_id, source_row))
            
        return issues
        
    @staticmethod
    def _validate_employee(record: Dict[str, Any], record_id: str, source_row: int) -> List[Dict[str, Any]]:
        issues = []
        # joining_date <= today
        jd = record.get("joining_date")
        if jd:
            try:
                dt = datetime.strptime(str(jd).split(" ")[0], "%Y-%m-%d").date()
                if dt > datetime.now().date():
                    issues.append(_create_issue(record_id, source_row, "joining_date", "Joining Date cannot be in the future", "BUSINESS_RULE_ERROR"))
            except Exception:
                pass
        return issues
        
    @staticmethod
    def _validate_vendor(record: Dict[str, Any], record_id: str, source_row: int) -> List[Dict[str, Any]]:
        issues = []
        sd = record.get("contract_start_date")
        ed = record.get("contract_end_date")
        if sd and ed:
            try:
                start_dt = datetime.strptime(str(sd).split(" ")[0], "%Y-%m-%d").date()
                end_dt = datetime.strptime(str(ed).split(" ")[0], "%Y-%m-%d").date()
                if end_dt < start_dt:
                    issues.append(_create_issue(record_id, source_row, "contract_end_date", "Contract End Date cannot be before Start Date", "BUSINESS_RULE_ERROR"))
            except Exception:
                pass
        return issues

    @staticmethod
    def _validate_client(record: Dict[str, Any], record_id: str, source_row: int) -> List[Dict[str, Any]]:
        issues = []
        # Reuse existing ClientValidationService for specialized checks

        from app.services.client_validation_service import ClientValidationService
        validation_result = ClientValidationService.validate_record(record, is_upload=True)
        if not validation_result.get("valid"):
            for err in validation_result.get("errors", []):
                # We skip missing field errors because the generic schema engine already handles required field errors!
                # We only want to bubble up business/formatting rules (like IFSC code invalid)
                if "is required" not in err.get("error", ""):
                    issues.append(_create_issue(record_id, source_row, err.get("field"), err.get("error"), "BUSINESS_RULE_ERROR"))
                elif err.get("error") == "Unsupported Excel column":
                    # Let the generic schema engine handle unknown columns if necessary, but actually the engine ignores them or we can flag them here.
                    issues.append(_create_issue(record_id, source_row, err.get("field"), err.get("error"), "UNSUPPORTED_COLUMN"))
        return issues
