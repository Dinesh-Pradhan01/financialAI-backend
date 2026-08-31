from typing import Dict, Any, List

class SchemaValidator:
    @staticmethod
    def validate_headers(actual_headers: List[str], schema: Dict[str, Any]):
        required_fields = [f["name"] for f in schema["fields"] if f.get("required", False)]
        
        missing = set(required_fields) - set(actual_headers)
        
        all_allowed_fields = set([f["name"] for f in schema["fields"]])
        unknown = set(actual_headers) - all_allowed_fields
        
        errors = []
        if missing:
            errors.append(f"Missing required headers: {', '.join(missing)}")
        if unknown:
            errors.append(f"Unknown headers present: {', '.join(unknown)}")
            
        if errors:
            raise ValueError(" | ".join(errors))
