import json
import os
from typing import Dict, Any, List

def load_schema(module_name: str) -> Dict[str, Any]:
    schema_path = os.path.join(os.path.dirname(__file__), "..", "config", "schemas", f"{module_name}_schema.json")
    if not os.path.exists(schema_path):
        raise ValueError(f"Schema for module '{module_name}' not found.")
    
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

class ParserFactory:
    @staticmethod
    def get_parser(file_extension: str):
        ext = file_extension.lower()
        if ext in [".xlsx", ".xls"]:
            from app.upload_engine.parsers.excel_parser import ExcelParser
            return ExcelParser()
        elif ext == ".csv":
            from app.upload_engine.parsers.csv_parser import CSVParser
            return CSVParser()
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")
