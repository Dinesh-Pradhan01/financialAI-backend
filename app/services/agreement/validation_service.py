from typing import Dict, Any
from app.services.agreement.schemas import ValidationResult
from loguru import logger
from datetime import datetime

class ValidationService:
    @staticmethod
    def validate_extraction(data: Dict[str, Any]) -> ValidationResult:
        errors = []
        ready_to_import = True
        
        # 1. Contract Value
        if data.get("contract_value") is not None:
            try:
                val = float(data["contract_value"])
                if val < 0:
                    errors.append("Contract value cannot be negative.")
                    ready_to_import = False
            except ValueError:
                errors.append("Contract value must be numeric.")
                ready_to_import = False

        # 2. Dates
        start_dt = None
        end_dt = None
        
        if data.get("contract_start_date"):
            try:
                start_dt = datetime.strptime(data["contract_start_date"], "%Y-%m-%d").date()
            except ValueError:
                errors.append("Invalid contract_start_date format.")
                ready_to_import = False
                
        if data.get("contract_end_date"):
            try:
                end_dt = datetime.strptime(data["contract_end_date"], "%Y-%m-%d").date()
            except ValueError:
                errors.append("Invalid contract_end_date format.")
                ready_to_import = False
                
        if start_dt and end_dt and end_dt < start_dt:
            errors.append("Contract end date cannot be before start date.")
            ready_to_import = False

        valid = len(errors) == 0

        return ValidationResult(
            valid=valid,
            errors=errors,
            ready_to_import=ready_to_import
        )
